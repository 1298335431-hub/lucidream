import assert from 'node:assert/strict';
import { test } from 'node:test';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.PREVIEW_URL || 'http://127.0.0.1:8443/';

test('real archive UI: retry, pagination, search, saved article/card, privacy and non-destructive new dream', async () => {
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ reducedMotion: 'reduce' });
    page.setDefaultTimeout(10000);
    const id = 'archive-test';
    const mutations = [];
    let unavailable = true;
    let incomplete = false;
    let articleReads = 0;
    const dream = { id, revision: 1, status: 'ready_to_generate', dream_text: '我在真实钟表店看见太阳',
      symbols: { dreamer: [], scenes: ['钟表店'], characters: [], objects: [], actions: [], emotions: [], relationships: [], reality_context: [], uncertain_fields: [] },
      character_appearance: 'male', character_form: '', created_at: '2026-09-14T00:00:00Z', model_mode: 'mock' };
    const entry = { ...dream, title: '账户自己的梦境', tags: ['钟表店'], interpretation_status: 'completed', image_status: 'completed', has_image: true };
    const interpretation = { session_id: id, revision: 1, generation_mode: 'personalized', interpretation: {
      title: entry.title, dream_summary: dream.dream_text, opening: '测试', reflections: ['已保存的真实解读'],
      card_summary: '只读验收', reflection_question: '有什么感受？', gentle_action: '记录下来', image_scene: '', image_style: '', style_reason: '' } };
    await page.route('**/*', async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.origin !== new URL(base).origin) return route.abort();
      if (!url.pathname.startsWith('/api/')) return route.continue();
      if (request.method() !== 'GET') mutations.push(request.method() + ' ' + url.pathname);
      if (url.pathname === '/api/v1/auth/me') return route.fulfill({ json: { account_id: 'archive-owner' } });
      if (url.pathname === '/api/v1/dreams') {
        if (unavailable) return route.fulfill({ status: 503, json: {} });
        if (url.searchParams.get('q')) return route.fulfill({ json: { dreams: [], total: 0, next_offset: null } });
        const second = url.searchParams.get('offset') === '1';
        const listed = incomplete ? { ...entry, interpretation_status: 'failed', image_status: null, has_image: false } : entry;
        return route.fulfill({ json: { dreams: [second ? { ...listed, id: 'second', title: '第二条已保存记录' } : listed], total: 2, next_offset: second ? null : 1 } });
      }
      if (url.pathname === `/api/v1/dreams/${id}`) return route.fulfill({ json: dream });
      if (url.pathname.endsWith('/interpretation')) { articleReads++; return route.fulfill({ json: interpretation }); }
      if (url.pathname.endsWith('/image')) return route.fulfill({ json: { session_id: id, revision: 1, status: 'completed', image_url: null } });
      return route.fulfill({ json: { total: 5, used: 1, remaining: 4 } });
    });
    const openModule = async (label) => page.getByRole('navigation', { name: '登录后主导航' }).getByRole('button', { name: label, exact: true }).click();
    await page.goto(base, { waitUntil: 'domcontentloaded' });
    await openModule('梦境册');
    await page.getByRole('button', { name: '重新连接', exact: true }).waitFor();
    assert.equal(await page.getByText('考场里的无声笔与未完成的答卷').count(), 0);
    unavailable = false;
    await page.getByRole('button', { name: '重新连接', exact: true }).click();
    await page.getByText(entry.title, { exact: true }).waitFor();
    await page.getByRole('button', { name: '加载更多记录' }).click();
    await page.getByText('第二条已保存记录', { exact: true }).waitFor();
    await page.getByRole('textbox', { name: '搜索梦境' }).fill('不存在');
    await page.getByRole('button', { name: '搜索', exact: true }).click();
    await page.getByText('没有找到相关梦境', { exact: true }).waitFor();
    await page.getByRole('button', { name: '清除搜索' }).click();
    await page.getByRole('button', { name: '查看解读', exact: true }).click();
    await page.locator('.interpretation-section').waitFor();
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('dreamcard.resultView')).view), 'interpretation');
    await openModule('梦境册');
    await page.getByRole('button', { name: '查看梦卡 / 下载', exact: true }).click();
    await page.locator('.dreamcard-area-heading').waitFor();
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('dreamcard.resultView')).view), 'dreamcard');
    incomplete = true;
    await openModule('梦境册');
    const beforeReads = articleReads;
    await page.getByRole('button', { name: '继续查看记录', exact: true }).click();
    await page.getByRole('heading', { name: /梦象已经确认/ }).waitFor();
    assert.equal(articleReads, beforeReads);
    assert.equal(await page.evaluate(() => JSON.parse(localStorage.getItem('dreamcard.resultView')).view), 'record');
    await openModule('设置隐私');
    await page.getByText('当前保存方式', { exact: true }).waitFor();
    assert.equal(await page.getByRole('switch').count(), 0);
    assert.equal(await page.getByRole('combobox').count(), 0);
    assert.equal(await page.getByRole('button', { name: '删除全部记录' }).count(), 0);
    assert.equal(await page.getByRole('button', { name: '导出我的数据' }).count(), 0);
    await page.setViewportSize({ width: 390, height: 844 });
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await openModule('梦境册');
    await page.getByText(entry.title, { exact: true }).waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole('button', { name: '记录新的梦境' }).click();
    await page.getByRole('textbox', { name: '梦境内容' }).waitFor();
    assert.equal(await page.evaluate(() => localStorage.getItem('dreamcard.recentSession')), null);
    assert.deepEqual(mutations, []);
  } finally { await browser.close(); }
});
