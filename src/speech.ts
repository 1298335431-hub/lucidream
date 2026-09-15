export type SpeechStatus = "idle" | "starting" | "listening" | "stopping";
export type SpeechIssue = { title: string; message: string };
export type SpeechResult = { isFinal: boolean; 0: { transcript: string } };
export type SpeechResultEvent = { resultIndex: number; results: ArrayLike<SpeechResult> };
export type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onstart: (() => void) | null;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onerror: ((event: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
export type RecognitionConstructor = new () => Recognition;
export const MAX_DREAM_CHARS = 300;

export function speechIssue(code: string): SpeechIssue {
  switch (code) {
    case "unsupported":
      return { title: "当前浏览器暂不支持语音转写", message: "可以继续文字输入，或用支持语音识别的浏览器打开此页面后重试。" };
    case "not-allowed":
    case "service-not-allowed":
      return { title: "语音访问未获允许", message: "请检查浏览器的网站麦克风权限及系统麦克风权限；若已允许，可能是浏览器的语音服务受限。现有文字已保留。" };
    case "audio-capture":
      return { title: "暂时无法使用麦克风", message: "请确认麦克风已连接、系统输入设备选择正确，且没有被其他程序独占，再试一次。" };
    case "network":
      return { title: "语音服务暂时连接不上", message: "请检查网络后重试。浏览器转写可能需要在线服务，现有文字已保留。" };
    case "no-speech":
      return { title: "这次没有听清", message: "请靠近麦克风说一句完整的话，再稍作停顿；也可以继续文字输入。" };
    case "language-not-supported":
      return { title: "当前语音服务不支持中文识别", message: "请更换支持中文语音识别的浏览器，或继续文字输入。" };
    case "incomplete":
      return { title: "最后一句尚未确认", message: "语音服务未返回最后一句的完整结果，已确认的文字已保留。请重新说一遍最后一句，或手动补充。" };
    case "timeout":
      return { title: "语音服务响应较慢", message: "请检查麦克风授权和网络后重试。已确认的文字已保留，你也可以继续文字输入。" };
    case "limit":
      return { title: `已达到 ${MAX_DREAM_CHARS} 字上限`, message: "现有内容已保留，请先精简一些文字，再继续记录。" };
    default:
      return { title: "语音转写暂时中断", message: "已确认的文字已保留。请稍后重试，或继续文字输入。" };
  }
}

export function appendSpeech(base: string, addition: string): string {
  if (!addition) return base;
  return `${base}${base && !/\s$/.test(base) ? " " : ""}${addition}`.slice(0, MAX_DREAM_CHARS);
}

// A session owns its callbacks. Late results from a cancelled session cannot
// change text after the user switches to typing or starts another recording.
export function startSpeechSession(recognition: Recognition, callbacks: {
  onStatus: (status: SpeechStatus) => void;
  onFinal: (text: string) => void;
  onInterim: (text: string) => void;
  onIssue: (issue: SpeechIssue) => void;
}) {
  let active = true;
  let stopping = false;
  let interim = "";
  const committed = new Set<number>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  const clearTimer = () => { if (timer !== undefined) clearTimeout(timer); };
  const finish = (abort: boolean, issue?: SpeechIssue) => {
    if (!active) return;
    active = false;
    clearTimer();
    recognition.onstart = recognition.onresult = recognition.onerror = recognition.onend = null;
    if (abort) { try { recognition.abort(); } catch { /* Already closed. */ } }
    callbacks.onInterim("");
    callbacks.onStatus("idle");
    if (issue) callbacks.onIssue(issue);
  };
  recognition.lang = "zh-CN";
  recognition.interimResults = true;
  recognition.continuous = true;
  recognition.onstart = () => {
    if (!active || stopping) return;
    clearTimer();
    callbacks.onStatus("listening");
  };
  recognition.onresult = (event) => {
    if (!active) return;
    const finalized: string[] = [];
    for (let index = event.resultIndex; index < event.results.length; index++) {
      const result = event.results[index];
      if (result.isFinal && !committed.has(index)) {
        committed.add(index);
        finalized.push(result[0].transcript);
      }
    }
    interim = Array.from(event.results).filter((result) => !result.isFinal).map((result) => result[0].transcript).join("");
    if (finalized.length) callbacks.onFinal(finalized.join(""));
    callbacks.onInterim(interim);
  };
  recognition.onerror = ({ error }) => {
    if (!active) return;
    finish(true, error === "aborted" && stopping ? undefined : speechIssue(error));
  };
  recognition.onend = () => {
    if (!active) return;
    finish(false, interim ? speechIssue("incomplete") : !stopping && committed.size === 0 ? speechIssue("no-speech") : undefined);
  };
  callbacks.onStatus("starting");
  timer = setTimeout(() => finish(true, speechIssue("timeout")), 12000);
  try { recognition.start(); }
  catch (error) {
    finish(true, speechIssue(error instanceof Error && error.name === "NotAllowedError" ? "not-allowed" : "unknown"));
  }
  return {
    stop() {
      if (!active || stopping) return;
      stopping = true;
      clearTimer();
      callbacks.onStatus("stopping");
      timer = setTimeout(() => finish(true, speechIssue("timeout")), 5000);
      try { recognition.stop(); } catch { finish(true, speechIssue("unknown")); }
    },
    dispose() { finish(true); },
  };
}
