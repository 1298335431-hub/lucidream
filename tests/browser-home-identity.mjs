import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const width of [1440, 390, 320]) {
  test(`home identity and composer remain usable at ${width}px`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: 'reduce' });
      const mutations = [], errors = [];
      page.on('pageerror', error => errors.push(error.message));
      // Keep this UI check independent of the external web-font service.
      await page.route('https://fonts.googleapis.com/**', route => route.abort());
      await page.route('https://fonts.gstatic.com/**', route => route.abort());
      await page.route('**/api/**', route => {
        if (route.request().method() !== 'GET') mutations.push(route.request().url());
        return route.fulfill({ status: 401, json: { error: { code: 'authentication_required', message: '请先登录' } } });
      });
      await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
      const hero = page.locator('#record');
      await hero.getByText('梦境回声', { exact: true }).waitFor();
      await page.waitForTimeout(1100);
      assert.match(await hero.innerText(), /看山说梦/);
      assert.match(await hero.innerText(), /带着梦卡去知乎/);
      for (const selector of ['.hero-introduction', '.hero-input-hint', '.hero-disclaimer']) {
        assert.ok(!(await hero.locator(selector).innerText()).endsWith('。'));
      }
      assert.equal(await hero.locator('.hero-input-hint').innerText(), '记得多少，就写多少');
      assert.equal(await hero.locator('.hero-input-hint').evaluate(el => getComputedStyle(el).marginTop), '36px', 'Keep the introduction-to-input spacing compact');
      // Semantic chunks stay together even when narrow screens wrap the paragraph.
      for (const chunk of await hero.locator('.hero-introduction > span').all()) {
        assert.equal(await chunk.evaluate(el => getComputedStyle(el).whiteSpace), 'nowrap');
      }
      assert.equal(await hero.locator('.composer-kanshan .kanshan-logo').count(), 1);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const input = page.getByRole('textbox', { name: '梦境内容' });
      assert.match(await input.getAttribute('aria-describedby'), /dream-composer-hint/);
      await hero.getByRole('button', { name: '玻璃森林', exact: true }).click();
      assert.match(await input.inputValue(), /透明的森林/);
      await input.fill('我在云朵上开了一家书店。');
      assert.equal(await input.inputValue(), '我在云朵上开了一家书店。');
      const hint = await hero.locator('.hero-input-hint').boundingBox();
      const hintText = await hero.locator('.hero-input-hint').evaluate(el => {
        const range = document.createRange(); range.selectNodeContents(el);
        const { x, y, width, height } = range.getBoundingClientRect();
        const css = getComputedStyle(el);
        return { x, y, width, height, border: css.borderTopWidth, background: css.backgroundColor };
      });
      assert.equal(hintText.border, '0px');
      assert.equal(hintText.background, 'rgba(0, 0, 0, 0)');
      const composer = await hero.locator('.composer-row').boundingBox();
      const mascot = await hero.locator('.composer-kanshan').boundingBox();
      assert.ok(Math.abs(mascot.y + mascot.height - composer.y - 3) < 1, 'Mascot should stand on the input top edge');
      assert.ok(mascot.x >= 0 && mascot.x + mascot.width <= width);
      assert.ok(mascot.x + mascot.width <= hintText.x || mascot.y + mascot.height <= hintText.y, 'Mascot must not cover the input hint text');
      await hero.getByRole('button', { name: '和刘看山一起记录梦境' }).click();
      assert.equal(await input.evaluate(el => el === document.activeElement), true);
      await page.screenshot({ path: `/tmp/home-identity-${width}.png` });
      assert.ok(composer.y >= hint.y + hint.height + 10, JSON.stringify({hint,composer}));
      await input.fill('');
      await input.blur();
      await page.screenshot({ path: `/tmp/home-identity-${width}.png` });
      assert.deepEqual(mutations, []);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}
