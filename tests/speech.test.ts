import assert from "node:assert/strict";
import { test } from "node:test";
import { appendSpeech, MAX_DREAM_CHARS, speechIssue, startSpeechSession, type Recognition, type SpeechIssue, type SpeechResult, type SpeechStatus } from "../src/speech.ts";

function fixture() {
  const states: SpeechStatus[] = [];
  const issues: SpeechIssue[] = [];
  let text = "原有梦境";
  let interim = "";
  let aborted = 0;
  const recognition: Recognition = {
    lang: "", interimResults: false, continuous: false,
    onstart: null, onresult: null, onerror: null, onend: null,
    start() {}, stop() {}, abort() { aborted++; },
  };
  const callbacks = {
    onStatus: (value: SpeechStatus) => states.push(value),
    onFinal: (value: string) => { text = appendSpeech(text, value); },
    onInterim: (value: string) => { interim = value; },
    onIssue: (value: SpeechIssue) => issues.push(value),
  };
  return { recognition, callbacks, states, issues, read: () => ({ text, interim, aborted }) };
}
const result = (transcript: string, isFinal: boolean): SpeechResult => ({ 0: { transcript }, isFinal });

test("interim revisions replace each other; cumulative finals never duplicate", () => {
  const f = fixture();
  const session = startSpeechSession(f.recognition, f.callbacks);
  try {
    assert.equal(f.recognition.interimResults, true);
    f.recognition.onstart?.();
    f.recognition.onresult?.({ resultIndex: 0, results: [result("树林", false)] });
    f.recognition.onresult?.({ resultIndex: 0, results: [result("一片树林", false)] });
    assert.equal(f.read().text, "原有梦境");
    assert.equal(f.read().interim, "一片树林");
    f.recognition.onresult?.({ resultIndex: 0, results: [result("一片树林", true)] });
    f.recognition.onresult?.({ resultIndex: 1, results: [result("一片树林", true), result("银色鹿", false)] });
    f.recognition.onresult?.({ resultIndex: 1, results: [result("一片树林", true), result("银色鹿群", true)] });
    f.recognition.onresult?.({ resultIndex: 0, results: [result("一片树林", true), result("银色鹿群", true)] });
    assert.equal(f.read().text, "原有梦境 一片树林 银色鹿群");
    assert.equal(f.read().interim, "");
  } finally { session.dispose(); }
});

test("stopping waits for the final result before returning to idle", () => {
  const f = fixture();
  const session = startSpeechSession(f.recognition, f.callbacks);
  f.recognition.onstart?.();
  f.recognition.onresult?.({ resultIndex: 0, results: [result("月亮", false)] });
  session.stop();
  assert.equal(f.states.at(-1), "stopping");
  f.recognition.onresult?.({ resultIndex: 0, results: [result("月亮", true)] });
  f.recognition.onend?.();
  assert.equal(f.read().text, "原有梦境 月亮");
  assert.equal(f.states.at(-1), "idle");
  assert.equal(f.issues.length, 0);
});

test("cancelled sessions cannot overwrite manual edits or a new session", () => {
  const f = fixture();
  const session = startSpeechSession(f.recognition, f.callbacks);
  const staleResult = f.recognition.onresult;
  const staleEnd = f.recognition.onend;
  session.dispose();
  const stateCount = f.states.length;
  staleResult?.({ resultIndex: 0, results: [result("过期结果", true)] });
  staleEnd?.();
  assert.equal(f.read().text, "原有梦境");
  assert.equal(f.states.length, stateCount);
  assert.equal(f.read().aborted, 1);
});

test("network and permission errors preserve final text and clear provisional text", () => {
  for (const code of ["network", "not-allowed", "audio-capture", "language-not-supported"]) {
    const f = fixture();
    startSpeechSession(f.recognition, f.callbacks);
    f.recognition.onresult?.({ resultIndex: 0, results: [result("已确认", true), result("临时", false)] });
    f.recognition.onerror?.({ error: code });
    assert.equal(f.read().text, "原有梦境 已确认");
    assert.equal(f.read().interim, "");
    assert.equal(f.states.at(-1), "idle");
    assert.deepEqual(f.issues, [speechIssue(code)]);
  }
});

test("synchronous start failure does not leave the button stuck listening", () => {
  const f = fixture();
  f.recognition.start = () => { throw new DOMException("denied", "NotAllowedError"); };
  startSpeechSession(f.recognition, f.callbacks);
  assert.equal(f.states.at(-1), "idle");
  assert.deepEqual(f.issues, [speechIssue("not-allowed")]);
});

test("silence and unfinished final utterance receive different guidance", () => {
  const silent = fixture();
  startSpeechSession(silent.recognition, silent.callbacks);
  silent.recognition.onend?.();
  assert.deepEqual(silent.issues, [speechIssue("no-speech")]);
  const incomplete = fixture();
  startSpeechSession(incomplete.recognition, incomplete.callbacks);
  incomplete.recognition.onresult?.({ resultIndex: 0, results: [result("未确认", false)] });
  incomplete.recognition.onend?.();
  assert.deepEqual(incomplete.issues, [speechIssue("incomplete")]);
});

test("start and stop watchdogs release a stalled session", (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const f = fixture();
  startSpeechSession(f.recognition, f.callbacks);
  t.mock.timers.tick(12000);
  assert.equal(f.states.at(-1), "idle");
  assert.deepEqual(f.issues, [speechIssue("timeout")]);
  const stopped = fixture();
  const session = startSpeechSession(stopped.recognition, stopped.callbacks);
  stopped.recognition.onstart?.();
  session.stop();
  t.mock.timers.tick(5000);
  assert.equal(stopped.states.at(-1), "idle");
});

test("voice append respects the product character limit and preserves typed newlines", () => {
  assert.equal(appendSpeech("梦".repeat(MAX_DREAM_CHARS - 1), "月光").length, MAX_DREAM_CHARS);
  assert.equal(appendSpeech("梦\n", "月光"), "梦\n月光");
  assert.equal(appendSpeech("原文", ""), "原文");
});
