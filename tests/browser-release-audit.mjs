// Read-only release audit using an isolated browser and intercepted API fixtures.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8443/';

async function fixture(view, viewport = { width: 1440, height: 1000 }, interrupted = false, panels = false, exhausted = false) {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport, reducedMotion: 'reduce' });
  page.setDefaultTimeout(15000);
  const id = 'release-audit';
  const mutations = [];
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(({ id, view }) => {
    if (localStorage.getItem('audit-initialized')) return;
    localStorage.setItem('audit-initialized', 'yes');
    localStorage.setItem('dreamcard.account', 'audit-account');
    localStorage.setItem('dreamcard.recentSession', id);
    localStorage.setItem('dreamcard.resultView', JSON.stringify({ sessionId: id, revision: 1, view }));
  }, { id, view });
  const dream = { id, revision: 1, status: 'ready_to_generate', dream_text: '我在钟表店里看见太阳',
    symbols: { dreamer: [], scenes: ['钟表店'], characters: [], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] },
    character_appearance: 'male', character_form: '', created_at: new Date().toISOString(), model_mode: 'mock' };
  await page.route('**/*', async route => {
    const request = route.request(), url = new URL(request.url());
    if (url.origin !== new URL(base).origin) return route.abort();
    if (!url.pathname.startsWith('/api/')) return route.continue();
    if (request.method() !== 'GET') mutations.push(request.method() + ' ' + url.pathname);
    if (exhausted && url.pathname.endsWith('/image')) {
      return request.method() === 'POST'
        ? route.fulfill({ status: 403, json: { error: { code: 'image_quota_exhausted', message: '此邀请码的 5 次生图额度已用完，已有梦卡仍可查看和下载' } } })
        : route.fulfill({ status: 404, json: { error: { code: 'image_not_found' } } });
    }
    if (interrupted && request.method() === 'GET' && url.pathname.endsWith('/interpretation')) {
      return route.fulfill({ status: 409, json: { error: { code: 'generation_interrupted', message: '上次解读已中断' } } });
    }
    if (url.pathname.endsWith('/image/file')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="540" height="720"><rect width="540" height="720" fill="#456789"/><circle cx="180" cy="180" r="80" fill="#d9b967"/></svg>' });
    const payload = url.pathname.endsWith('/auth/me') ? { account_id: 'audit-account' }
      : url.pathname.endsWith('/interpretation') ? { session_id: id, revision: 1, generation_mode: 'personalized', interpretation: {
        title: '上线验证梦卡', dream_summary: dream.dream_text, opening: '测试', reflections: ['已保存解读'], card_summary: '一段用于出卡验证的文字。', reflection_question: '梦里是什么感受？', gentle_action: '记录下来', image_scene: '', image_style: '', style_reason: '' } }
      : url.pathname.endsWith('/image') ? { session_id: id, revision: 1, status: 'completed', image_url: `/api/v1/dreams/${id}/image/file`, ...(panels ? { failure_reason: 'contains_panels', supplementary_attempts: 0, recovery_action: 'retry_generation' } : {}) }
      : request.method() === 'DELETE' ? { deleted: true } : dream;
    return route.fulfill({ json: payload });
  });
  await page.goto(base, { waitUntil: 'domcontentloaded' });
  return { browser, page, mutations, errors };
}

test('exhausted quota shows a short notice and preserves the article without a failed card', async () => {
  const { browser, page, mutations, errors } = await fixture('interpretation', undefined, false, false, true);
  try {
    await page.getByRole('button', { name: '制作梦卡', exact: true }).click();
    await page.getByRole('alert').getByText('额度不足', { exact: true }).waitFor();
    assert.ok(await page.getByRole('button', { name: '制作梦卡', exact: true }).isVisible());
    assert.equal(await page.locator('.dreamcard-studio-section').count(), 0);
    assert.deepEqual(mutations, ['POST /api/v1/dreams/release-audit/image']);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

test('article new-dream action preserves the previous backend record', async () => {
  const { browser, page, mutations } = await fixture('interpretation');
  try {
    page.on('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '记录另一个梦', exact: true }).click();
    await page.getByRole('textbox', { name: '梦境内容' }).waitFor();
    assert.deepEqual(mutations, []);
    assert.equal(await page.evaluate(() => localStorage.getItem('dreamcard.recentSession')), null);
  } finally { await browser.close(); }
});

for (const width of [1440, 390]) {
  test(`studio new-dream button returns to empty input without deleting history at ${width}px`, async () => {
    const { browser, page, mutations, errors } = await fixture('dreamcard', { width, height: 1000 });
    try {
      const footer = page.locator('.dreamcard-review-footer');
      await footer.getByRole('button', { name: '记录下一个梦境', exact: true }).waitFor();
      const first = await footer.getByRole('button', { name: '返回解梦文章', exact: true }).boundingBox();
      const next = await footer.getByRole('button', { name: '记录下一个梦境', exact: true }).boundingBox();
      assert.ok(next.y >= first.y + first.height + 10);
      await footer.getByRole('button', { name: '记录下一个梦境', exact: true }).click();
      const input = page.getByRole('textbox', { name: '梦境内容' });
      await input.waitFor();
      assert.equal(await input.inputValue(), '');
      assert.equal(await page.evaluate(() => localStorage.getItem('dreamcard.recentSession')), null);
      assert.deepEqual(mutations, []);
      assert.deepEqual(errors, []);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    } finally { await browser.close(); }
  });
}

test('interrupted interpretation restores saved dream without automatically generating', async () => {
  const { browser, page, mutations, errors } = await fixture('interpretation', undefined, true);
  try {
    await page.getByText('上次解读已中断，梦境内容已保留。请点击生成按钮重新开始解析。', { exact: true }).waitFor();
    await page.getByRole('button', { name: '生成这张梦卡', exact: true }).waitFor();
    assert.deepEqual(mutations, []);
    assert.deepEqual(errors, []);
    assert.equal(await page.evaluate(() => localStorage.getItem('dreamcard.recentSession')), 'release-audit');
  } finally { await browser.close(); }
});

test('panel warning retains preview and download, redraw needs confirmation', async () => {
  const { browser, page, mutations, errors } = await fixture('dreamcard', undefined, false, true);
  try {
    await page.locator('.dreamcard-review-warning').getByText(/画面可能出现分镜或拼接/).waitFor();
    assert.equal(await page.locator('.dreamcard-export .dreamcard-artwork img').count(), 1);
    assert.equal(await page.getByRole('button', { name: '下载梦卡', exact: true }).isEnabled(), true);
    await page.getByRole('button', { name: '重新生成一次', exact: true }).click();
    await page.getByRole('button', { name: '确认补生成', exact: true }).waitFor();
    assert.deepEqual(mutations, []);
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.locator('.dreamcard-review-warning').getByText(/画面可能出现分镜或拼接/).waitFor();
    const pending = page.waitForEvent('download');
    await page.getByRole('button', { name: '下载梦卡', exact: true }).click();
    const png = await readFile(await (await pending).path());
    assert.equal(png.readUInt32BE(16), 1080);
    assert.deepEqual(mutations, []);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});

for (const width of [1440, 390]) {
  test(`download at ${width}px: date/label preferences, refresh and 1080x1440 PNG`, async () => {
    const { browser, page, mutations, errors } = await fixture('dreamcard', { width, height: 1000 });
    try {
      await page.locator('.dreamcard-area-heading').waitFor();
      const mascot = page.locator('.dreamcard-export .dreamcard-label img');
      await mascot.waitFor();
      assert.match(await mascot.getAttribute('src'), /idle-static\.png$/);
      assert.equal(await mascot.getAttribute('alt'), '刘看山');
      await mascot.evaluate(image => image.decode());
      await page.getByRole('button', { name: '画面调整', exact: true }).click();
      await page.getByRole('switch', { name: '显示梦境日期', exact: true }).uncheck();
      await page.getByRole('switch', { name: '显示左下角小看山', exact: true }).uncheck();
      await page.getByRole('button', { name: '完成', exact: true }).click();
      await page.reload({ waitUntil: 'domcontentloaded' });
      await page.locator('.dreamcard-area-heading').waitFor();
      const settings = await page.evaluate(() => JSON.parse(localStorage.getItem('dreamcard.textSettings'))['release-audit']);
      assert.equal(settings.showDate, false); assert.equal(settings.showLabel, false);
      assert.equal(await page.locator('.dreamcard-export time').count(), 0);
      assert.equal(await page.locator('.dreamcard-export .dreamcard-label').count(), 0);
      const pending = page.waitForEvent('download', { timeout: 30000 });
      await page.getByRole('button', { name: '下载梦卡', exact: true }).click();
      const download = await pending;
      const png = await readFile(await download.path());
      assert.equal(png.subarray(1, 4).toString(), 'PNG');
      assert.equal(png.readUInt32BE(16), 1080); assert.equal(png.readUInt32BE(20), 1440);
      assert.deepEqual(mutations, []); assert.deepEqual(errors, []);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    } finally { await browser.close(); }
  });
}
