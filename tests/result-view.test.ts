import assert from "node:assert/strict";
import { test } from "node:test";
import { clearResultView, readResultView, saveResultView } from "../src/result-view.ts";

function fixture() {
  const values = new Map<string, string>();
  return {
    values,
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => { values.set(key, value); },
    removeItem: (key: string) => { values.delete(key); },
  };
}

test("refresh restores the dreamcard view for the same dream revision", () => {
  const storage = fixture();
  saveResultView(storage, "dream-1", 2, "dreamcard");
  assert.equal(readResultView(storage, "dream-1", 2), "dreamcard");
});

test("returning to interpretation replaces the studio preference", () => {
  const storage = fixture();
  saveResultView(storage, "dream-1", 2, "dreamcard");
  saveResultView(storage, "dream-1", 2, "interpretation");
  assert.equal(readResultView(storage, "dream-1", 2), "interpretation");
});

test("incomplete archive entries can explicitly reopen saved facts", () => {
  const storage = fixture();
  saveResultView(storage, "draft-1", 1, "record");
  assert.equal(readResultView(storage, "draft-1", 1), "record");
  assert.equal(readResultView(storage, "draft-1", 2), null);
});

test("another dream or edited revision does not inherit the old view", () => {
  const storage = fixture();
  saveResultView(storage, "dream-1", 2, "dreamcard");
  assert.equal(readResultView(storage, "dream-2", 2), null);
  assert.equal(readResultView(storage, "dream-1", 3), null);
});

test("logout and a fresh login clear only navigation, not other saved data", () => {
  const storage = fixture();
  storage.setItem("dreamcard.textSettings", "retained");
  saveResultView(storage, "dream-1", 2, "dreamcard");
  clearResultView(storage);
  assert.equal(readResultView(storage, "dream-1", 2), null);
  assert.equal(storage.getItem("dreamcard.textSettings"), "retained");
});

test("missing, malformed, and unsupported preferences can fall back safely", () => {
  const storage = fixture();
  assert.equal(readResultView(storage, "dream-1", 2), null);
  storage.setItem("dreamcard.resultView", "invalid json");
  assert.equal(readResultView(storage, "dream-1", 2), null);
  storage.setItem("dreamcard.resultView", JSON.stringify({ sessionId: "dream-1", revision: 2, view: "unknown" }));
  assert.equal(readResultView(storage, "dream-1", 2), null);
});

test("storage errors do not block navigation", () => {
  const fail = () => { throw new Error("storage unavailable"); };
  const storage = { getItem: fail, setItem: fail, removeItem: fail };
  assert.equal(readResultView(storage, "dream-1", 2), null);
  assert.doesNotThrow(() => saveResultView(storage, "dream-1", 2, "dreamcard"));
  assert.doesNotThrow(() => clearResultView(storage));
});
