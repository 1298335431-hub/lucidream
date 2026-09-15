import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const [width, outcome] of [[1440, 'completed'], [390, 'completed'], [1440, 'failed']]) {
  test(`studio generation ${outcome}: immediate entry and safe controls at ${width}px`, async () => {
    const browser = await chromium.launch();
    let releaseImage;
    const imageGate = new Promise(resolve => { releaseImage = resolve; });
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const errors = [], posts = [];
      let started = false, completed = false, imageRequested = false;
      page.on('pageerror', error => errors.push(error.message));
      await page.addInitScript(() => {
        localStorage.setItem('dreamcard.account', 'studio-fixture');
        localStorage.setItem('dreamcard.recentSession', 'studio-fixture');
        localStorage.setItem('dreamcard.resultView', JSON.stringify({ sessionId: 'studio-fixture', revision: 1, view: 'interpretation' }));
      });
      await page.route('**/*', async route => {
        const request = route.request(), url = new URL(request.url());
        if (url.origin !== 'http://127.0.0.1:8443') return route.abort();
        if (!url.pathname.startsWith('/api/')) return route.continue();
        if (request.method() === 'POST') { posts.push(url.pathname); started = true; }
        if (url.pathname.endsWith('/auth/me')) return route.fulfill({ json: { account_id: 'studio-fixture' } });
        if (url.pathname.endsWith('/interpretation')) return route.fulfill({ json: { session_id: 'studio-fixture', revision: 1, generation_mode: 'personalized', interpretation: { title: '云上的书店', dream_summary: '云上有一家书店', reflections: ['一段测试解读'], card_summary: '一段测试解读', reflection_question: '醒来是什么感受？' } } });
        if (url.pathname.endsWith('/image/file')) {
          imageRequested = true;
          await imageGate;
          return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="540" height="720"><rect width="540" height="720" fill="#456789"/></svg>' });
        }
        if (url.pathname.endsWith('/image')) return started
          ? route.fulfill({ json: { session_id: 'studio-fixture', revision: 1, status: completed ? outcome : 'processing', image_url: completed && outcome === 'completed' ? '/api/v1/dreams/studio-fixture/image/file' : null, retry_after_seconds: .15 } })
          : route.fulfill({ status: 404, json: { error: { code: 'image_not_found' } } });
        return route.fulfill({ json: { id: 'studio-fixture', revision: 1, status: 'ready_to_generate', dream_text: '云上有一家书店', created_at: '2026-09-15T08:00:00Z', model_mode: 'mock', symbols: { dreamer: [], scenes: [], characters: [], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] } } });
      });
      await page.goto('http://127.0.0.1:8443/');
      await page.getByRole('button', { name: '制作梦卡', exact: true }).click();
      const studio = page.getByRole('region', { name: '梦卡制作', exact: true });
      await studio.waitFor();
      const sideButtons = page.locator('.dreamcard-toolbar button:visible, .dreamcard-review-warning button:visible');
      assert.ok(await sideButtons.count() >= 8);
      for (const button of await sideButtons.all()) assert.equal(await button.isEnabled(), false);
      assert.equal(await page.locator('.dreamcard-review-warning [data-guide-scene="card"]').getAttribute('data-guide-action'), 'ball');
      await page.screenshot({ path: `/tmp/studio-generating-${width}.png` });
      completed = true;
      if (outcome === 'failed') {
        const back = page.locator('.dreamcard-review-footer').getByRole('button', { name: '返回解梦文章', exact: true });
        await page.waitForFunction(() => !document.querySelector('.dreamcard-review-footer button')?.disabled);
        assert.equal(await page.getByRole('button', { name: '下载梦卡', exact: true }).isEnabled(), false);
        await back.click();
        await page.getByRole('button', { name: '制作梦卡', exact: true }).waitFor();
        assert.deepEqual(posts, ['/api/v1/dreams/studio-fixture/image']);
        assert.deepEqual(errors, []);
        return;
      }
      await page.waitForFunction(() => Boolean(document.querySelector('.dreamcard-artwork > img')));
      assert.equal(imageRequested, true);
      for (const button of await sideButtons.all()) assert.equal(await button.isEnabled(), false, 'Backend completion is not the same as a loaded image');
      releaseImage();
      await page.waitForFunction(() => !document.querySelector('.dreamcard-compact-tools button:last-child')?.disabled);
      for (const button of await sideButtons.all()) assert.equal(await button.isEnabled(), true);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: `/tmp/studio-ready-${width}.png` });
      assert.deepEqual(posts, ['/api/v1/dreams/studio-fixture/image']);
      assert.deepEqual(errors, []);
    } finally { releaseImage(); await browser.close(); }
  });
}
