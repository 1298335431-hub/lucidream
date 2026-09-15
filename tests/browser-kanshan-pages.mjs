// Isolated fixtures: no real login, dream creation, image generation or publishing.
import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = 'http://127.0.0.1:8443/';

async function fixture(browser, scene, width = 1440, motion = 'reduce') {
  const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: motion });
  const errors = [], writes = [];
  page.on('pageerror', error => errors.push(error.message));
  const session = { id: 'guide-fixture', revision: 1, status: scene === 'review' ? 'reviewing_symbols' : 'ready_to_generate',
    dream_text: '我在云端书店遇见一只会说话的狐狸', created_at: '2026-09-15T08:00:00Z', model_mode: 'mock',
    symbols: { dreamer: ['一个人'], scenes: ['云端书店'], characters: ['狐狸'], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] } };
  if (scene === 'safety') { session.status = 'safety_interrupted'; session.safety_message = '测试提示'; }
  await page.addInitScript(({ scene, id }) => {
    if (['review', 'confirmed', 'reading', 'card', 'loading', 'safety'].includes(scene)) {
      localStorage.setItem('dreamcard.account', 'guide-account');
      localStorage.setItem('dreamcard.recentSession', id);
      localStorage.setItem('dreamcard.resultView', JSON.stringify({ sessionId: id, revision: 1, view: ['card', 'loading'].includes(scene) ? 'dreamcard' : scene === 'reading' ? 'interpretation' : 'record' }));
    }
  }, { scene, id: session.id });
  await page.route('**/*', route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== new URL(base).origin) return route.abort();
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (request.method() !== 'GET') { writes.push(url.pathname); return route.abort(); }
    if (url.pathname.endsWith('/auth/me')) return route.fulfill({ status: scene === 'login' ? 401 : 200, json: scene === 'login' ? {} : { account_id: 'guide-account' } });
    if (url.pathname.endsWith('/account/quota')) return route.fulfill({ json: { total: 8, used: 1, remaining: 7 } });
    if (url.pathname.endsWith('/dreams')) return route.fulfill({ json: { dreams: [], total: 0, next_offset: null } });
    if (url.pathname.endsWith('/interpretation')) return route.fulfill({ json: { session_id: session.id, revision: 1, generation_mode: 'personalized', interpretation: { title: '云端书店里的相遇', dream_summary: session.dream_text, opening: '测试', reflections: ['一段测试解读'], card_summary: '一段测试解读', reflection_question: '醒来有什么感受？', gentle_action: '记录下来' } } });
    if (url.pathname.endsWith('/image/file')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="540" height="720"><rect width="540" height="720" fill="#456789"/></svg>' });
    if (url.pathname.endsWith('/image')) return route.fulfill({ json: { session_id: session.id, revision: 1, status: scene === 'loading' ? 'processing' : 'completed', image_url: scene === 'loading' ? null : '/api/v1/dreams/guide-fixture/image/file', retry_after_seconds: 30 } });
    return route.fulfill({ json: session });
  });
  if (motion === 'no-preference') await page.clock.install();
  await page.goto(`${base}${scene === 'login' ? '#invite' : ''}`);
  return { page, errors, writes };
}

for (const width of [1440, 390, 320]) {
  test(`page guides are in flow, distinct and outside the export at ${width}px`, async () => {
    const browser = await chromium.launch();
    try {
      for (const [scene, action] of Object.entries({ login: 'wave', review: 'sway', confirmed: 'wave', reading: 'sway', card: 'ball', loading: 'ball', safety: 'idle' })) {
        const { page, errors, writes } = await fixture(browser, scene, width);
        const guide = page.locator(`[data-guide-scene="${scene === 'loading' ? 'card' : scene}"]`);
        await guide.scrollIntoViewIfNeeded();
        assert.equal(await guide.getAttribute('data-guide-action'), action);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        const bounds = await guide.boundingBox();
        assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width + 1);
        assert.equal(await page.locator('.dreamcard-export .kanshan-page-guide').count(), 0);
        if (scene === 'reading') {
          const titleLines = await page.locator('.interpretation-section > h1').evaluate(el => {
            const rows = new Map(), node = el.firstChild;
            for (let i = 0; i < node.textContent.length; i++) {
              const range = document.createRange(); range.setStart(node, i); range.setEnd(node, i + 1);
              const y = Math.round(range.getBoundingClientRect().y);
              rows.set(y, (rows.get(y) || '') + node.textContent[i]);
            }
            return [...rows.values()];
          });
          assert.ok(titleLines.every(line => line.length > 1), `No lone character in title: ${titleLines}`);
          const character = await guide.locator('button').boundingBox();
          const card = await page.locator('.interpretation-reading-column > .interpretation-card').boundingBox();
          const speech = await guide.locator('.kanshan-speech').boundingBox();
          assert.ok(Math.abs(character.y + character.height - card.y) <= 2, 'Feet sit on the article divider');
          assert.ok(Math.abs(character.x + character.width - card.x - card.width) <= 2, 'Mascot sits at the right end');
          assert.ok(speech.x + speech.width <= character.x, 'Speech sits left of the mascot');
        }
        await page.screenshot({ path: `/tmp/kanshan-${scene}-${width}.png` });
        assert.deepEqual(errors, []); assert.deepEqual(writes, []);
        await page.close();
      }
      const { page, errors, writes } = await fixture(browser, 'account', width);
      for (const [name, scene, action] of [['账户额度', 'account', 'idle'], ['梦境册', 'archive', 'sleep'], ['设置隐私', 'privacy', 'idle']]) {
        await page.getByRole('button', { name, exact: true }).click();
        const guide = page.locator(`[data-guide-scene="${scene}"]`);
        await guide.scrollIntoViewIfNeeded();
        assert.equal(await guide.getAttribute('data-guide-action'), action);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: `/tmp/kanshan-${scene}-${width}.png` });
      }
      assert.deepEqual(errors, []); assert.deepEqual(writes, []);
    } finally { await browser.close(); }
  });
}

for (const [scene, duration] of [['reading', 3000], ['review', 3000], ['card', 4000]]) {
test(`${scene} guide greets, rests eight seconds and resets the rest after a click`, async () => {
  const browser = await chromium.launch();
  try {
    const { page, errors, writes } = await fixture(browser, scene, 1440, 'no-preference');
    const guide = page.locator(`[data-guide-scene="${scene}"]`);
    await guide.scrollIntoViewIfNeeded();
    await guide.locator('img').waitFor();
    await guide.locator('img').evaluate(img => img.decode());
    await page.clock.fastForward(duration);
    await guide.locator('canvas').waitFor();
    await page.clock.fastForward(7900);
    assert.equal(await guide.locator('img').count(), 0);
    await page.clock.fastForward(100);
    await guide.locator('img').waitFor();
    await guide.locator('img').evaluate(img => img.decode());
    await page.clock.fastForward(duration);
    await guide.locator('canvas').waitFor();
    await page.clock.fastForward(4000);
    await guide.getByRole('button').click();
    await guide.locator('img').waitFor();
    await guide.locator('img').evaluate(img => img.decode());
    await page.clock.fastForward(duration);
    await guide.locator('canvas').waitFor();
    await page.clock.fastForward(7900);
    assert.equal(await guide.locator('img').count(), 0);
    await page.clock.fastForward(100);
    await guide.locator('img').waitFor();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await guide.locator('canvas').waitFor();
    await guide.getByRole('button').click();
    assert.equal(await guide.locator('img').count(), 0);
    assert.deepEqual(errors, []); assert.deepEqual(writes, []);
  } finally { await browser.close(); }
});
}
