import test from 'node:test';
import assert from 'node:assert/strict';
import { createLogin, publicCallback, profileFromUser, parseProviderJSON } from '../lib/login.mjs';

// Synthetic accounts matching the official user_info PDF; no live account data.
const base = { oauth: { enabled: true, appId: '760', redirectUri: 'https://dream.example.com/auth/callback', identityPath: ['uid'], callbackRegistered: true } };
function setup(config = base, overrides = {}) {
  let time = 1000;
  const calls = [];
  const login = createLogin(config, {
    credentials: async () => ({ appKey: 'test-key', accessSecret: 'test-secret' }),
    now: () => time,
    request: async (url, init) => {
      calls.push({ url, init });
      return url.endsWith('access_token') ? { code: 20000, data: { access_token: 'test-token', expires_in: 3600 } }
        : { uid: 123456789, fullname: '测试用户', avatar_path: 'https://picx.zhimg.com/example.jpg', email: 'private@example.com', phone_no: 'private' };
    }, ...overrides,
  });
  return { login, calls, setTime: value => { time = value; } };
}
async function flow(login) {
  const start = await login.start();
  const url = new URL(start.authorization_url);
  assert.equal(url.origin, 'https://openapi.zhihu.com');
  assert.equal(url.searchParams.get('app_id'), '760');
  assert.ok(!start.authorization_url.includes('test-key'));
  return { flow_id: start.flow_id, state: url.searchParams.get('state'), authorization_code: 'test-code' };
}

test('deployment, credentials and identity contract are required', async () => {
  for (const [config, overrides, expected] of [
    [{ oauth: { ...base.oauth, redirectUri: null } }, {}, 'deployment_required'],
    [base, { credentials: async () => ({}) }, 'credentials_required'],
    [{ oauth: { ...base.oauth, identityPath: null } }, {}, 'identity_contract_required'],
    [{ oauth: { ...base.oauth, callbackRegistered: false } }, {}, 'callback_registration_required'],
  ]) {
    const { login, calls } = setup(config, overrides);
    assert.equal((await login.status()).code, expected);
    await assert.rejects(login.start(), { code: expected });
    assert.equal(calls.length, 0);
  }
});
test('callback addresses reject local, credentials, fragments and arbitrary paths', () => {
  for (const url of ['http://dream.example.com/auth/callback', 'https://localhost/auth/callback', 'https://127.0.0.1/auth/callback', 'https://[::1]/auth/callback', 'https://10.0.0.1/auth/callback', 'https://192.168.1.1/auth/callback', 'https://dream.local/auth/callback', 'https://a:b@dream.example.com/auth/callback', 'https://dream.example.com/auth/callback?x=1', 'https://dream.example.com/auth/callback#x', 'https://dream.example.com/elsewhere']) assert.equal(publicCallback(url), false, url);
});
test('documented uid and OAuth bearer, minimal profile, one-time callback', async () => {
  const { login, calls } = setup();
  const input = await flow(login);
  const result = await login.callback(input);
  assert.deepEqual(result, { provider: 'zhihu', subject: '123456789', profile: {provider: 'zhihu', nickname: '测试用户', avatarUrl: 'https://picx.zhimg.com/example.jpg'}, verified: true, session_seconds: 3600 });
  const form = new URLSearchParams(calls[0].init.body);
  assert.equal(form.get('code'), 'test-code');
  assert.equal(form.get('app_key'), 'test-key');
  assert.deepEqual(calls[1].init.headers, { Authorization: 'Bearer test-token' });
  assert.ok(!JSON.stringify(result).includes('private'));
  assert.ok(!JSON.stringify(result).includes('test-token'));
  await assert.rejects(login.callback(input), { code: 'flow_expired' });
  assert.equal(calls.length, 2);
});
for (const [change, expected] of [[{ state: '' }, 'state_missing'], [{ state: 'wrong' }, 'state_mismatch'], [{ authorization_code: '' }, 'code_missing'], [{ error: 'denied' }, 'authorization_denied']]) {
  test(`reject ${expected} before contacting provider`, async () => {
    const { login, calls } = setup();
    const input = await flow(login);
    await assert.rejects(login.callback({ ...input, ...change }), { code: expected });
    assert.equal(calls.length, 0);
    await assert.rejects(login.callback(input), { code: 'flow_expired' });
  });
}
test('expired and foreign-browser flow cannot establish identity', async () => {
  const { login, setTime, calls } = setup();
  const input = await flow(login);
  await assert.rejects(login.callback({ ...input, flow_id: 'other' }), { code: 'flow_expired' });
  setTime(601001);
  await assert.rejects(login.callback(input), { code: 'flow_expired' });
  assert.equal(calls.length, 0);
});
test('parallel callbacks exchange the authorization code at most once', async () => {
  const { login, calls } = setup();
  const input = await flow(login);
  const results = await Promise.allSettled([login.callback(input), login.callback(input)]);
  assert.equal(results.filter(result => result.status === 'fulfilled').length, 1);
  assert.equal(calls.length, 2);
});
for (const profile of [{ fullname: 'nickname' }, { uid: 9007199254740992 }, { uid: 123, code: 401 }, { uid: 0 }, { uid: true }, { uid: '00123' }]) {
  test('never infer identity from a nickname, unsafe number or failed response', async () => {
    const { login } = setup(base, { request: async url => url.endsWith('access_token') ? { access_token: 'token', expires_in: 60 } : profile });
    await assert.rejects(login.callback(await flow(login)), { code: 'identity_invalid' });
  });
}
test('OAuth login no longer requires a developer Access Secret', async () => {
  const { login } = setup(base, { credentials: async () => ({ appKey: 'test-key' }) });
  assert.equal((await login.status()).ready, true);
});
test('large integer user IDs retain their exact identity before number rounding', () => {
  const result = parseProviderJSON('{"uid":2029619126742656657,"fullname":"测试"}');
  assert.equal(profileFromUser(result).subject, '2029619126742656657');
});
test('profile accepts a precise string ID but drops unsafe avatars and extra fields', () => {
  assert.deepEqual(profileFromUser({ uid: '2029619126742656657', fullname: ' 小山 ', avatar_path: 'https://evil.example/avatar', email: 'private' }),
    { subject: '2029619126742656657', profile: {provider: 'zhihu', nickname: '小山'} });
  for (const avatar_path of ['javascript:alert(1)', 'http://picx.zhimg.com/a', 'https://picx.zhimg.com.evil.example/a', 'https://u:p@picx.zhimg.com/a']) {
    assert.equal(profileFromUser({uid: 1, avatar_path}).profile.avatarUrl, undefined);
  }
});
test('a failed token business response is rejected even if it contains a token', async () => {
  const { login } = setup(base, { request: async () => ({code: 401, access_token: 'token', expires_in: 60}) });
  await assert.rejects(login.callback(await flow(login)), {code: 'upstream_failed'});
});
test('provider error bodies are never shown to browser', async () => {
  const { login } = setup(base, { request: async () => { throw new Error('secret-provider-body'); } });
  await assert.rejects(login.callback(await flow(login)), error => error.code === 'upstream_failed' && !error.message.includes('secret-provider-body'));
});
