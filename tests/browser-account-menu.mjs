import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

test('verified backend nickname and avatar are used, not URL profile parameters', async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
    await page.route('https://picx.zhimg.com/**', route => route.abort());
    await page.route('**/api/v1/**', route => route.fulfill({json: route.request().url().endsWith('/auth/me')
      ? {account_id: 'synthetic-zhihu-account', profile: {provider: 'zhihu', nickname: '接口测试用户', avatarUrl: 'https://picx.zhimg.com/test-avatar.jpg'}} : {}}));
    await page.goto('http://127.0.0.1:8443/?nickname=不可信昵称');
    await page.getByRole('button', {name: '接口测试用户，账号菜单'}).click();
    assert.ok(await page.getByText('通过知乎登录', {exact: true}).isVisible());
    assert.equal(await page.getByText('不可信昵称', {exact: true}).count(), 0);
  } finally { await browser.close(); }
});

for (const width of [1440, 390, 320]) {
  test(`account menu navigation, dismissal and logout confirmation at ${width}px`, async () => {
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      const errors = [];
      const writes = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
      // Isolated browser fixtures only: no real login, quota or dream changes.
      await page.route('**/api/v1/**', route => {
        const request = route.request();
        if (request.method() !== 'GET') writes.push(request.url());
        if (request.url().endsWith('/auth/me')) return route.fulfill({ json: { account_id: 'ui-test-only' } });
        if (request.url().endsWith('/account/quota')) return route.fulfill({ json: { total: 8, used: width === 320 ? 8 : 1, remaining: width === 320 ? 0 : 7 } });
        return route.fulfill({ json: {} });
      });
      await page.goto('http://127.0.0.1:8443/?v=account-menu-test');
      const trigger = page.getByRole('button', { name: '体验用户，账号菜单' });
      await trigger.waitFor();
      assert.equal(await page.locator('.profile-trigger-name').isVisible(), width > 640);
      await trigger.click();
      await page.getByRole('menu', { name: '账号操作' }).waitFor();
      assert.ok(await page.getByText('邀请码体验账户', { exact: true }).isVisible());
      const bounds = await page.locator('.profile-popover').boundingBox();
      assert.ok(bounds.x >= 0 && bounds.x + bounds.width <= width);
      assert.equal(await page.locator('.profile-popover').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
      await page.screenshot({ path: `/tmp/account-menu-${width}.png` });
      await page.keyboard.press('End');
      assert.equal(await page.locator(':focus').innerText(), '退出登录');
      await page.keyboard.press('Escape');
      assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
      assert.ok(await trigger.evaluate(el => el === document.activeElement));
      await page.keyboard.press('ArrowDown');
      await page.getByRole('menuitem', { name: '账户与额度' }).click();
      await page.getByText('剩余次数', { exact: true }).waitFor();
      await page.getByText('当前账户共 8 次生图额度', { exact: true }).waitFor();
      assert.ok(await page.getByText('免费体验', { exact: true }).isVisible());
      assert.equal(await page.getByText('额度不足', { exact: true }).count(), width === 320 ? 1 : 0);
      assert.equal(await page.locator('.account-workspace .workspace-heading strong').innerText(), width === 320 ? '0' : '7');
      assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
      await trigger.click();
      await page.getByRole('menuitem', { name: '隐私设置' }).click();
      await page.getByText('隐私与数据', { exact: true }).waitFor();
      await trigger.click();
      await page.getByText('隐私与数据', { exact: true }).click();
      assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
      await trigger.click();
      await page.getByRole('menuitem', { name: '退出登录' }).click();
      await page.getByRole('dialog', { name: '确定退出登录？' }).waitFor();
      await page.getByRole('button', { name: '取消', exact: true }).click();
      assert.ok(await trigger.isVisible());
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert.deepEqual(writes, []);
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}
