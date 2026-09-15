// Isolated browser fixture: run on a separate port from the real preview.
// All fetch calls are mocked, including image polling and validation.
const id = "result-view-test";
if (!localStorage.getItem("result-view-test.initialized")) {
  localStorage.setItem("result-view-test.initialized", "true");
  localStorage.setItem("lucidream.inviteAuthenticated", "true");
  localStorage.setItem("dreamcard.recentSession", id);
  localStorage.setItem("dreamcard.resultView", JSON.stringify({ sessionId: id, revision: 1, view: "dreamcard" }));
}

const session = {
  id, revision: 1, status: "ready_to_generate", dream_text: "我变成一只水母，在星空中游动。",
  symbols: { scenes: ["星空"], characters: ["水母"], objects: [], actions: ["游动"], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] },
  clarification: null, clarification_answer: null, character_appearance: "other", character_form: "水母",
  safety_message: null, created_at: "2026-09-14T00:00:00Z", model_mode: "test",
};
const interpretation = {
  session_id: id, revision: 1, generation_mode: "personalized",
  interpretation: {
    title: "星空中的水母", opening: "一段用于页面验证的梦。", dream_summary: session.dream_text,
    reflections: ["这是一条本地测试解读。"], card_summary: "这是测试页面，不会调用任何生成接口。",
    reflection_question: "梦里的你感受如何？", gentle_action: "记下梦中的颜色。", image_scene: "", image_style: "", style_reason: "",
  },
};

window.fetch = async (input, init) => {
  const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, location.href);
  const method = init?.method ?? (input instanceof Request ? input.method : "GET");
  if (method !== "GET") throw new Error(`Unexpected request in read-only fixture: ${method} ${url.pathname}`);
  const response = url.pathname === `/api/v1/dreams/${id}` ? session
    : url.pathname === `/api/v1/dreams/${id}/interpretation` ? interpretation
    : url.pathname === `/api/v1/dreams/${id}/image` ? {
      session_id: id, revision: 1, status: "completed", image_url: null,
      retry_after_seconds: null, failure_reason: "subject_mismatch",
    } : null;
  return Response.json(response ?? { detail: "Test endpoint not found" }, { status: response ? 200 : 404 });
};

await import("../src/main.tsx");
export {};
