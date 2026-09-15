// Run against a built local preview. Requests are intercepted; no real model calls.
// PLAYWRIGHT_MODULE may point to an installed Playwright index.mjs.
import assert from "node:assert/strict";
import { test } from "node:test";
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || "playwright");
const base = process.env.PREVIEW_URL || "http://127.0.0.1:8443/";
const id = "isolated-restore-test";
const view = JSON.stringify({ sessionId: id, revision: 1, view: "dreamcard" });
const session = {
  id, revision: 1, status: "ready_to_generate", dream_text: "测试梦境：我在星空中游动。",
  symbols: { scenes: ["星空"], dreamer: [], characters: [], objects: [], actions: ["游动"], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] },
  clarification: null, clarification_answer: null, character_appearance: "other", character_form: "章鱼",
  created_at: "2026-09-14T00:00:00Z", model_mode: "mock",
};
const interpretation = {
  session_id: id, revision: 1, generation_mode: "personalized",
  interpretation: { title: "恢复验收", opening: "测试", dream_summary: session.dream_text,
    reflections: ["测试解读"], card_summary: "仅用于恢复测试。", reflection_question: "有什么感受？",
    gentle_action: "记录下来", image_scene: "", image_style: "", style_reason: "" },
};

for (const status of [403, 404]) {
  test(`confirmed record ${status} clears only the inaccessible entry`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage();
      page.setDefaultTimeout(10000);
      await page.addInitScript(({ id, view }) => {
        localStorage.setItem("dreamcard.account", "isolated-account");
        localStorage.setItem("dreamcard.recentSession", id);
        localStorage.setItem("dreamcard.resultView", view);
        localStorage.setItem("dreamcard.textSettings", "{}");
      }, { id, view });
      await page.route("**/*", async (route) => {
        const url = new URL(route.request().url());
        if (url.origin !== new URL(base).origin) return route.abort();
        if (!url.pathname.startsWith("/api/")) return route.continue();
        return route.fulfill(url.pathname.endsWith("/auth/me")
          ? { json: { account_id: "isolated-account" } }
          : { status, json: { error: { message: "无法访问" } } });
      });
      await page.goto(base, { waitUntil: "domcontentloaded" });
      await page.getByRole("textbox", { name: "梦境内容" }).waitFor();
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.recentSession")), null);
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.resultView")), null);
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.textSettings")), "{}");
      assert.equal(await page.getByRole("button", { name: "重新连接" }).count(), 0);
    } finally { await browser.close(); }
  });
}

for (const stage of ["auth", "dream", "article", "image", "network"]) {
  test(`${stage} temporary failure preserves the entry and reconnect restores the studio`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ reducedMotion: "reduce" });
      page.setDefaultTimeout(10000);
      await page.addInitScript(({ id, view }) => {
        if (localStorage.getItem("acceptance.seeded")) return;
        localStorage.setItem("acceptance.seeded", "yes");
        localStorage.setItem("dreamcard.account", "isolated-account");
        localStorage.setItem("dreamcard.recentSession", id);
        localStorage.setItem("dreamcard.resultView", view);
      }, { id, view });
      let failing = true;
      const mutations = [];
      await page.route("**/*", async (route) => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.origin !== new URL(base).origin) return route.abort();
        if (!url.pathname.startsWith("/api/")) return route.continue();
        if (request.method() !== "GET") mutations.push(request.method() + " " + url.pathname);
        const path = url.pathname;
        const current = path.endsWith("/auth/me") ? "auth" : path.endsWith("/interpretation") ? "article"
          : path.endsWith("/image") ? "image" : path === `/api/v1/dreams/${id}` ? "dream" : "other";
        if (failing && stage === "network" && current === "dream") return route.abort("internetdisconnected");
        if (failing && current === stage) return route.fulfill({ status: 503, json: { error: { message: "临时故障" } } });
        const data = current === "auth" ? { account_id: "isolated-account" } : current === "dream" ? session
          : current === "article" ? interpretation : current === "image" ? { session_id: id, revision: 1, status: "completed", image_url: null }
          : { total: 5, used: 1, remaining: 4 };
        return route.fulfill({ json: data });
      });
      await page.goto(base, { waitUntil: "domcontentloaded" });
      await page.getByRole("button", { name: "重新连接", exact: true }).waitFor();
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.recentSession")), id);
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.resultView")), view);
      failing = false;
      await page.getByRole("button", { name: "重新连接", exact: true }).click();
      await page.locator(".dreamcard-area-heading").waitFor();
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.recentSession")), id);
      assert.equal(await page.evaluate(() => localStorage.getItem("dreamcard.resultView")), view);
      assert.deepEqual(mutations, []);
    } finally { await browser.close(); }
  });
}
