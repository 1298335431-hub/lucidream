import { test } from 'node:test';
import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');

for (const width of [1440, 390, 320]) {
  test(`Zhihu entry and existing invite remain usable at ${width}px`, async () => {
    const browser = await chromium.launch();
    try {
      const page = await browser.newPage({ viewport: { width, height: 900 }, reducedMotion: 'reduce' });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
      // Isolated contract fixture: do not depend on a running OAuth companion.
      await page.route('**/api/v1/auth/zhihu/status', route => route.fulfill({ json: { ready: false, code: 'callback_registration_required', message: '知乎登录回调尚未登记，暂不可用' } }));
      await page.goto('http://127.0.0.1:8443/?v=zhihu-login-1#invite');
      await page.getByText('知乎登录回调尚未登记，暂不可用', { exact: true }).waitFor();
      const login = page.getByRole('button', { name: '使用知乎账号登录' });
      assert.equal(await login.getAttribute('aria-disabled'), 'true');
      await login.evaluate(button => button.click());
      assert.match(page.url(), /#invite$/);
      assert.ok(await page.getByRole('textbox', { name: '邀请码' }).isVisible());
      await page.route('**/api/v1/auth/login', route => route.fulfill({ status: 401, json: { error: { message: '邀请码无效或已停用' } } }));
      await page.getByRole('textbox', { name: '邀请码' }).fill('not-real');
      await page.getByRole('button', { name: '提交邀请码' }).click();
      await page.getByText('邀请码无效或已停用', { exact: true }).waitFor();
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await page.screenshot({ path: `/tmp/zhihu-login-${width}.png`, fullPage: true });
      await page.getByRole('button', { name: '返回首页', exact: true }).click();
      await page.getByRole('textbox', { name: '梦境内容' }).waitFor();
      assert.deepEqual(errors, []);
    } finally { await browser.close(); }
  });
}

test('login request uses backend URL and does not replace a draft', async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
    await page.addInitScript(() => localStorage.setItem('dreamcard.draft', '测试中保留的梦境'));
    await page.route('**/api/v1/auth/zhihu/status', route => route.fulfill({ json: { ready: true, code: null, message: '使用知乎账号登录，保存你的梦境' } }));
    let starts = 0;
    await page.route('**/api/v1/auth/zhihu/start', route => {
      starts++;
      return route.fulfill({ json: { authorization_url: 'https://openapi.zhihu.com/authorize?app_id=760&state=fictional' } });
    });
    await page.route('https://openapi.zhihu.com/**', route => route.fulfill({ contentType: 'text/html', body: '<p>Mock authorization page</p>' }));
    await page.goto('http://127.0.0.1:8443/#invite');
    await page.getByText('使用知乎账号登录，保存你的梦境', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => localStorage.getItem('dreamcard.draft')), '测试中保留的梦境');
    await page.getByRole('button', { name: '使用知乎账号登录' }).click();
    await page.waitForURL('https://openapi.zhihu.com/**');
    assert.equal(starts, 1);
  } finally { await browser.close(); }
});

test('callback error, untrusted redirect and disconnected status do not pretend to log in', async () => {
  const browser = await chromium.launch();
  try {
    const page = await browser.newPage();
    await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\//, route => route.abort());
    await page.route('**/api/v1/auth/zhihu/status', route => route.fulfill({ json: { ready: true, message: 'Ready' } }));
    await page.route('**/api/v1/auth/zhihu/start', route => route.fulfill({ json: { authorization_url: 'https://evil.example/' } }));
    await page.goto('http://127.0.0.1:8443/?zhihu=state_missing#invite');
    await page.getByText('授权回调缺少安全校验信息，未建立登录', { exact: true }).waitFor();
    await page.getByRole('button', { name: '使用知乎账号登录' }).click();
    await page.getByText(/^暂时无法前往知乎，请(?:稍后重试|重试或使用邀请码)$/).waitFor();
    assert.match(page.url(), /127\.0\.0\.1/);
    await page.route('**/api/v1/auth/zhihu/status', route => route.abort());
    await page.reload();
    await page.getByRole('button', { name: '重新检查' }).waitFor();
    assert.equal(await page.getByRole('button', { name: '使用知乎账号登录' }).getAttribute('aria-disabled'), 'true');
  } finally { await browser.close(); }
});
