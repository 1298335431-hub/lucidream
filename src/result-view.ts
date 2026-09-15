type ResultView = "record" | "interpretation" | "dreamcard";
type ViewStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

const RESULT_VIEW_KEY = "dreamcard.resultView";

export function readResultView(storage: ViewStorage, sessionId: string, revision: number): ResultView | null {
  try {
    const saved = JSON.parse(storage.getItem(RESULT_VIEW_KEY) ?? "null");
    if (saved?.sessionId === sessionId && saved.revision === revision &&
      (saved.view === "record" || saved.view === "interpretation" || saved.view === "dreamcard")) return saved.view;
  } catch {
    // A missing or unavailable browser preference must not block the dream.
  }
  return null;
}

export function saveResultView(storage: ViewStorage, sessionId: string, revision: number, view: ResultView) {
  try {
    storage.setItem(RESULT_VIEW_KEY, JSON.stringify({ sessionId, revision, view }));
  } catch {
    // The backend record remains available even if local storage is full.
  }
}

export function clearResultView(storage: ViewStorage) {
  try {
    storage.removeItem(RESULT_VIEW_KEY);
  } catch {
    // Navigation should still work when browser storage is unavailable.
  }
}
