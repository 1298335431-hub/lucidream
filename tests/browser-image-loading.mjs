// Isolated HTTP fixtures: image recovery must never submit another generation.
import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const [width, recovery] of [[1440, 'reload'], [390, 'late'], [320, 'return']]) {
  test(`image download timeout unlocks recovery: ${recovery} at ${width}px`, async () => {
    const browser = await chromium.launch();
    const releases = [], writes = [], errors = [];
    let imageRequests = 0;
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      await page.clock.install();
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('dreamcard.account', 'image-timeout');
        localStorage.setItem('dreamcard.recentSession', 'image-timeout');
        localStorage.setItem('dreamcard.resultView', JSON.stringify({ sessionId: 'image-timeout', revision: 1, view: 'dreamcard' }));
      });
      await page.route('**/*', async route => {
        const req = route.request(), url = new URL(req.url());
        if (url.origin !== 'http://127.0.0.1:8443') return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        if (req.method() !== 'GET') { writes.push(req.method() + url.pathname); return route.abort(); }
        if (url.pathname.endsWith('/auth/me')) return route.fulfill({ json: { account_id: 'image-timeout' } });
        if (url.pathname.endsWith('/interpretation')) return route.fulfill({ json: { session_id: 'image-timeout', revision: 1, generation_mode: 'personalized', interpretation: { title: '云端书店里的相遇', dream_summary: '我在云端书店', reflections: ['测试解读'], card_summary: '解读仍然保留', reflection_question: '醒来是什么感受？' } } });
        if (url.pathname.endsWith('/image')) return route.fulfill({ json: { session_id: 'image-timeout', revision: 1, status: 'completed', image_url: '/api/v1/dreams/image-timeout/image/file' } });
        if (url.pathname.endsWith('/image/file')) {
          imageRequests++;
          await new Promise(resolve => releases.push(resolve));
          return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="540" height="720"><rect width="540" height="720" fill="#456789"/></svg>' }).catch(() => {});
        }
        return route.fulfill({ json: { id: 'image-timeout', revision: 1, status: 'ready_to_generate', dream_text: '我在云端书店', created_at: '2026-09-15T00:00:00Z', symbols: { dreamer: [], scenes: [], characters: [], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] } } });
      });
      await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
      const sidebar = page.locator('.dreamcard-review-warning');
      await sidebar.getByText('正在载入图片', { exact: true }).waitFor();
      const back = page.locator('.dreamcard-review-footer').getByRole('button', { name: '返回解梦文章', exact: true });
      assert.equal(await back.isEnabled(), false);
      await page.clock.fastForward(21000);
      await sidebar.getByText('图片加载超时', { exact: true }).waitFor();
      assert.equal(await page.locator('.dreamcard-copy').isVisible(), false, 'Card text cannot cover recovery controls');
      assert.equal(await back.isEnabled(), true);
      assert.equal(await page.getByRole('button', { name: '下载梦卡', exact: true }).isEnabled(), false);
      assert.equal(await page.getByRole('button', { name: '准备分享到知乎', exact: true }).isEnabled(), false);
      await page.screenshot({ path: `/tmp/image-timeout-${width}.png` });
      if (recovery === 'return') {
        await back.click();
        await page.locator('.interpretation-section').waitFor();
        await page.clock.fastForward(60000);
        assert.equal(await page.locator('.dreamcard-studio-section').count(), 0);
        assert.equal(await page.evaluate(() => localStorage.getItem('dreamcard.recentSession')), 'image-timeout');
      } else {
        if (recovery === 'reload') {
          const request = page.waitForRequest(req => req.url().includes('/image/file'));
          await page.getByRole('button', { name: '重新载入图片', exact: true }).click();
          await request;
          assert.equal(await back.isEnabled(), false);
          // The new attempt receives its own complete deadline.
          await page.clock.fastForward(10000);
          assert.equal(await sidebar.getByText('图片加载超时', { exact: true }).count(), 0);
          releases.at(-1)();
        } else releases[0]();
        await sidebar.getByText('图片已生成', { exact: true }).waitFor();
        assert.equal(await page.getByRole('button', { name: '下载梦卡', exact: true }).isEnabled(), true);
        assert.equal(await page.getByRole('button', { name: '准备分享到知乎', exact: true }).isEnabled(), true);
        await page.clock.fastForward(60000);
        assert.equal(await sidebar.getByText('图片加载超时', { exact: true }).count(), 0);
      }
      assert.equal(imageRequests, recovery === 'reload' ? 2 : 1);
      assert.deepEqual(writes, []); assert.deepEqual(errors, []);
    } finally { releases.forEach(release => release()); await browser.close(); }
  });
}
