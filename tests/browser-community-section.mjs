import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const width of [1440, 768, 390, 320]) {
  test(`community introduction, sample and navigation at ${width}px`, async () => {
    const browser = await chromium.launch({ headless: true });
    try {
      const page = await browser.newPage({ viewport: { width, height: 1000 }, reducedMotion: width === 1440 ? 'no-preference' : 'reduce' });
      const mutations = [], errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
      await page.route('**/api/**', route => {
        if (route.request().method() !== 'GET') mutations.push(route.request().url());
        return route.fulfill({ status: 401, json: { error: { code: 'authentication_required' } } });
      });
      await page.goto('http://127.0.0.1:8443/', { waitUntil: 'domcontentloaded' });
      const input = page.getByRole('textbox', { name: '梦境内容' });
      await input.fill('梦里有一扇半开的门');
      assert.equal(await page.locator('.pricing-card, .pricing-mode').count(), 0);
      assert.ok(!(await page.locator('.site-header').innerText()).includes('定价'));
      const share = page.locator('.site-header a').filter({ hasText: '分享与共鸣' });
      if (!(await share.first().isVisible())) await page.locator('svg.tabler-icon-menu-2').click();
      const links = await page.locator('.site-header a').filter({ visible: true }).allTextContents();
      assert.ok(links.findIndex(text => text.includes('分享与共鸣')) < links.findIndex(text => text.includes('方法与来源')), 'Sharing should precede sources in navigation');
      assert.deepEqual(await page.locator('.home-story > section').evaluateAll(nodes => nodes.map(node => node.id)), ['process', 'showcase', 'pricing', 'sources', 'experience']);
      await share.filter({ visible: true }).first().click();
      const section = page.locator('.community-section');
      await page.waitForTimeout(1700);
      assert.ok(await section.locator('h2').isVisible());
      assert.ok(await section.locator('h2').evaluate(el => el.getBoundingClientRect().top >= 70));
      assert.match((await section.textContent()).replace(/\s/g, ''), /带到知乎聊聊/);
      assert.match(await section.locator('.community-zhihu-mark img').getAttribute('src'), /assets\/zhihu\/wordmark.svg$/);
      assert.match(await section.innerText(), /图文仅为分享示例，未发布至知乎/);
      assert.match(await section.textContent(), /只分享你愿意公开的内容/);
      assert.ok(!/Plus|Pro|月付|年付|一键发布|¥/.test(await section.innerText()));
      await section.locator('.community-card-image').scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector('.community-card-image')?.naturalWidth > 0);
      const card = await section.locator('.community-card-image').boundingBox();
      const mascot = await section.locator('.community-kanshan').boundingBox();
      assert.ok(Math.abs(mascot.y + mascot.height - card.y - 2) < 1, 'Mascot feet should meet the card edge');
      assert.ok(mascot.x >= card.x && mascot.x + mascot.width < card.x + card.width);
      assert.ok(await section.locator('.community-zhihu-mark img').evaluate(el => el.naturalWidth > 0));
      await section.locator('.community-bottom').scrollIntoViewIfNeeded();
      await page.waitForTimeout(1200);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      // Scroll groups back through the viewport before the full-section capture.
      await section.locator('.community-example').scrollIntoViewIfNeeded();
      await page.waitForTimeout(1200);
      await section.screenshot({ path: `/tmp/community-section-${width}.png` });
      await section.getByRole('button', { name: '制作我的梦卡' }).click();
      await page.waitForFunction(() => document.activeElement?.getAttribute('aria-label') === '梦境内容');
      await page.waitForTimeout(1000);
      assert.equal(await input.inputValue(), '梦里有一扇半开的门');
      assert.ok((await input.boundingBox()).y >= 0);
      assert.deepEqual(errors, []);
      assert.deepEqual(mutations, []);
    } finally { await browser.close(); }
  });
}
