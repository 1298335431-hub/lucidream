import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const width of [1440, 390]) {
  test(`closing experience returns to the dream input at ${width}px`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, hasTouch: width === 390, reducedMotion: 'reduce' });
      const mutations = [], errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
      await page.route('**/api/**', route => {
        if (route.request().method() !== 'GET') mutations.push(route.request().url());
        return route.fulfill({ status: 401, json: { error: { code: 'authentication_required' } } });
      });
      await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
      const input = page.getByRole('textbox', { name: '梦境内容' });
      await input.fill('我在云朵上开了一家书店');
      const start = page.getByRole('button', { name: '立即体验', exact: true });
      for (const activation of width === 390 ? ['touch'] : ['click', 'keyboard']) {
        await start.scrollIntoViewIfNeeded();
        assert.ok(await page.evaluate(() => scrollY > 1000));
        if (activation === 'touch') await start.tap();
        else if (activation === 'keyboard') { await start.focus(); await page.keyboard.press('Enter'); }
        else await start.click();
        await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === '梦境内容');
        await page.waitForTimeout(1000);
        const box = await input.boundingBox();
        assert.ok(box.y >= 0 && box.y + box.height <= 1000, 'Input should be in the first-screen viewport');
        assert.equal(await input.inputValue(), '我在云朵上开了一家书店', 'Navigation must preserve the draft');
        assert.ok(!page.url().includes('#invite'), 'Experience must not redirect to login');
      }
      assert.deepEqual(errors, []);
      assert.deepEqual(mutations, []);
    } finally { await browser.close(); }
  });
}
