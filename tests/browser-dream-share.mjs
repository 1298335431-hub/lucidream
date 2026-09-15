import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const width of [1440, 390, 320]) {
  test(`share preview is editable, private by default and exports a real card at ${width}px`, async () => {
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const writes = [], errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('dreamcard.account', 'share-test');
        localStorage.setItem('dreamcard.recentSession', 'share-dream');
        localStorage.setItem('dreamcard.resultView', JSON.stringify({ sessionId: 'share-dream', revision: 1, view: 'dreamcard' }));
        Object.defineProperty(navigator, 'clipboard', { value: { writeText: async text => { window.copiedShareText = text; } }, configurable: true });
      });
      const session = { id: 'share-dream', revision: 1, status: 'ready_to_generate', dream_text: '不可自动公开的原始梦境',
        symbols: { dreamer: [], scenes: [], characters: [], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] },
        character_appearance: 'unspecified', created_at: '2026-09-15T00:00:00Z', model_mode: 'mock' };
      await page.route('**/*', route => {
        const req = route.request(), url = new URL(req.url());
        if (url.origin !== 'http://127.0.0.1:8443') return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        if (req.method() !== 'GET') writes.push(req.method() + url.pathname);
        if (url.pathname.endsWith('/image/file')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="540" height="720"><rect width="540" height="720" fill="#456789"/><circle cx="180" cy="180" r="80" fill="#f4ddab"/></svg>' });
        const data = url.pathname.endsWith('/auth/me') ? { account_id: 'share-test' }
          : url.pathname.endsWith('/interpretation') ? { session_id: session.id, revision: 1, generation_mode: 'personalized', interpretation: { title: '云端洗衣店', dream_summary: session.dream_text, reflections: ['测试解读'], card_summary: '只在主动勾选后加入文案的解读', reflection_question: '醒来是什么感受？' } }
          : url.pathname.endsWith('/image') ? { session_id: session.id, revision: 1, status: 'completed', image_url: '/api/v1/dreams/share-dream/image/file' } : session;
        return route.fulfill({ json: data });
      });
      await page.goto('http://127.0.0.1:8443/?v=share-ui-test');
      const entry = page.getByRole('button', { name: '准备分享到知乎', exact: true });
      await entry.locator('.dream-share-zhihu-mark').waitFor();
      await entry.locator('.dream-share-zhihu-mark').evaluate(img => img.decode());
      assert.match(await entry.locator('img').getAttribute('src'), /assets\/zhihu\/wordmark\.svg$/);
      await entry.click();
      const dialog = page.getByRole('dialog', { name: '把这场梦，整理成故事' });
      await dialog.waitFor();
      const image = dialog.getByAltText('当前选中的完整梦卡，包含画面和卡上解读');
      await image.waitFor({ timeout: 20000 });
      assert.deepEqual(await image.evaluate(img => [img.naturalWidth, img.naturalHeight]), [1080, 1440]);
      assert.ok(await image.evaluate(img => {
        const canvas = document.createElement('canvas'); canvas.width = img.naturalWidth; canvas.height = img.naturalHeight;
        const ctx = canvas.getContext('2d'); ctx.drawImage(img, 0, 0);
        return [[.9,.5],[.5,.9],[.9,.9]].every(([x,y]) => ctx.getImageData(Math.floor(x*canvas.width), Math.floor(y*canvas.height), 1, 1).data[3] === 255);
      }), 'card must fill the exported canvas on mobile, not just have correct file dimensions');
      assert.equal(await dialog.getByLabel('想分享的梦境故事', { exact: true }).inputValue(), '');
      const preview = dialog.getByLabel('文案预览');
      assert.equal(await preview.inputValue(), '云端洗衣店');
      await dialog.getByLabel('标题', { exact: true }).fill('我的奇遇');
      await dialog.getByLabel('想分享的梦境故事', { exact: true }).fill('洗衣机洗出了会唱歌的云');
      const checkbox = dialog.getByRole('checkbox');
      assert.equal(await checkbox.isChecked(), false);
      await checkbox.check();
      assert.match(await preview.inputValue(), /只在主动勾选后加入文案的解读/);
      await checkbox.uncheck();
      await dialog.getByRole('button', { name: '复制文案', exact: true }).click();
      assert.equal(await page.evaluate(() => window.copiedShareText), '我的奇遇\n\n洗衣机洗出了会唱歌的云');
      assert.ok(await dialog.getByText('文案已复制，尚未发布到知乎', { exact: true }).isVisible());
      const pending = page.waitForEvent('download');
      await dialog.getByRole('button', { name: '下载梦卡', exact: true }).click();
      const download = await pending;
      const png = await readFile(await download.path());
      assert.equal(png.readUInt32BE(16), 1080); assert.equal(png.readUInt32BE(20), 1440);
      const zhihuLink = dialog.getByRole('link', { name: '打开知乎（新窗口）' });
      assert.equal(await zhihuLink.getAttribute('href'), 'https://www.zhihu.com/');
      assert.equal(await zhihuLink.getAttribute('rel'), 'noopener noreferrer');
      await page.context().route('https://www.zhihu.com/**', route => route.fulfill({contentType: 'text/html', body: '<p>Isolated destination fixture</p>'}));
      const newPage = page.context().waitForEvent('page');
      await zhihuLink.click();
      const destination = await newPage;
      await destination.waitForLoadState();
      assert.equal(destination.url(), 'https://www.zhihu.com/');
      assert.equal(await destination.evaluate(() => window.opener), null);
      await destination.close();
      assert.equal(await preview.inputValue(), '我的奇遇\n\n洗衣机洗出了会唱歌的云');
      await page.evaluate(() => { navigator.clipboard.writeText = async () => { throw new Error('denied'); }; });
      await dialog.getByRole('button', { name: '复制文案', exact: true }).click();
      assert.ok(await dialog.getByText('复制未成功，请在文案预览中长按或选中文字复制', { exact: true }).isVisible());
      assert.ok(await dialog.evaluate(el => el.scrollWidth <= el.clientWidth));
      await dialog.evaluate(el => { el.scrollTop = 0; });
      await page.screenshot({ path: `/tmp/dream-share-${width}.png` });
      await zhihuLink.scrollIntoViewIfNeeded();
      await page.screenshot({ path: `/tmp/dream-share-actions-${width}.png` });
      // Native modal keeps keyboard focus inside, then restores it on Escape.
      await page.keyboard.press('Tab');
      assert.ok(await dialog.evaluate(el => el.contains(document.activeElement)));
      await page.keyboard.press('Escape');
      assert.equal(await dialog.count(), 0);
      await entry.click();
      assert.equal(await page.getByLabel('想分享的梦境故事', { exact: true }).inputValue(), '洗衣机洗出了会唱歌的云');
      await page.getByRole('button', { name: '关闭分享预览' }).click();
      await page.screenshot({ path: `/tmp/dream-share-entry-${width}.png` });
      assert.deepEqual(writes, []); assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}
