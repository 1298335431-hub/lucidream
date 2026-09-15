import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const touch of [false, true]) {
  test(`Kanshan seated computer animation and ${touch ? 'touch' : 'hover'} behavior`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width: touch ? 390 : 1440, height: 1000 }, hasTouch: touch, reducedMotion: 'no-preference' });
      await page.route('**/api/**', route => route.fulfill({ status: 401, json: { error: { code: 'authentication_required' } } }));
      await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
      await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
      const logo = page.locator('.composer-kanshan img.kanshan-logo');
      await logo.waitFor();
      assert.match(await logo.getAttribute('src'), /^blob:/);
      assert.equal(await page.locator('.site-header img.kanshan-logo').count(), 0);
      assert.equal(await page.locator('.site-header .kanshan-logo').count(), 0);
      assert.ok(await page.locator('.site-header .dream-card-logo').count() > 0);
      await page.waitForFunction(() => [...document.querySelectorAll('img.kanshan-logo')].every(img => img.complete && img.naturalWidth === 320));
      const first = await logo.screenshot();
      await page.waitForTimeout(900);
      assert.notDeepEqual(await logo.screenshot(), first, 'GIF should actually animate');
      if (touch) {
        await logo.tap();
        assert.match(await logo.getAttribute('src'), /^blob:/);
        assert.equal(await page.getByRole('textbox', { name: '梦境内容' }).evaluate(el => el === document.activeElement), true);
      } else {
        const originalBox = await logo.boundingBox();
        await logo.hover();
        assert.match(await logo.getAttribute('src'), /^blob:/, 'Hover must not switch back to the standing mascot');
        await page.waitForTimeout(400);
        assert.deepEqual(await logo.boundingBox(), originalBox, 'Hover must not move the mascot');
        await page.screenshot({ path: '/tmp/kanshan-computer-preview.png' });
        await page.mouse.move(700, 600);
        assert.match(await logo.getAttribute('src'), /^blob:/);
        await logo.click();
        assert.equal(await page.getByRole('textbox', { name: '梦境内容' }).evaluate(el => el === document.activeElement), true);
      }
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.locator('.composer-kanshan canvas.kanshan-logo').waitFor();
      assert.equal(await page.locator('img.kanshan-logo').count(), 0);
      await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.locator('.composer-kanshan img.kanshan-logo').waitFor();
    } finally { await browser.close(); }
  });
}

for (const width of [1440, 390]) {
  test(`navigation restores the original static brand logo at ${width}px`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
      await page.route('**/api/**', route => route.fulfill({ status: 401, json: { error: { code: 'authentication_required', message: '请先登录' } } }));
      await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
      const logo = page.locator('.site-header .dream-card-logo:visible').first();
      await logo.waitFor();
      const before = await logo.evaluate(svg => svg.outerHTML);
      await page.waitForTimeout(350);
      assert.equal(await logo.evaluate(svg => svg.outerHTML), before);
      assert.equal(await logo.evaluate(svg => svg.classList.contains('is-animated')), false);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.match(await page.locator('.site-header').innerText(), /LUCIDREAM/);
      assert.equal(await page.locator('.site-header .kanshan-logo').count(), 0);
      assert.deepEqual(errors, []);
      await page.screenshot({ path: `/tmp/kanshan-nav-${width}.png` });
      await page.getByRole('button', { name: '返回 LUCIDREAM 首页' }).filter({ visible: true }).first().click();
      await page.getByRole('textbox', { name: '梦境内容' }).waitFor();
    } finally { await browser.close(); }
  });
}
