import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

test('card mascot waves on arrival, rests, supports clicks, and stops offscreen', async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
    await page.route('**/api/**', route => route.fulfill({ status: 401, json: { error: { code: 'authentication_required' } } }));
    await page.clock.install();
    await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
    const button = page.locator('.community-kanshan');
    assert.equal(await button.locator('img').count(), 0, 'Offscreen mascot should not animate');
    await page.getByRole('link', { name: '分享与共鸣' }).filter({ visible: true }).click();
    await button.locator('img').waitFor({ timeout: 5000 });
    await page.waitForFunction(() => document.querySelector('.community-kanshan img')?.complete);
    assert.equal(await button.locator('img').evaluate(el => el.naturalWidth), 320);
    await page.clock.fastForward(4000);
    await button.locator('canvas').waitFor();
    await page.clock.fastForward(7000);
    assert.equal(await button.locator('img').count(), 0);
    await button.click();
    await button.locator('img').waitFor();
    await page.waitForFunction(() => document.querySelector('.community-kanshan img')?.complete);
    const url = await button.locator('img').getAttribute('src');
    await button.click();
    assert.equal(await button.locator('img').getAttribute('src'), url);
    await page.clock.fastForward(4000);
    await button.locator('canvas').waitFor();
    await page.clock.fastForward(8000);
    await button.locator('img').waitFor();
    await page.locator('#record').evaluate(el => el.scrollIntoView({ behavior: 'instant' }));
    await button.locator('canvas').waitFor({ state: 'attached' });
    await page.clock.fastForward(20000);
    assert.equal(await button.locator('img').count(), 0);
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
});
