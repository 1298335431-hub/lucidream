// Application login adapter. The bundled Skill and its demo remain unmodified.
// Tokens never leave this Node process; only a verified, stable subject is returned.
import { execFile } from 'node:child_process';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { isIP } from 'node:net';

export const messages = {
  deployment_required: '知乎登录等待部署并配置公网回调，本地暂不可用',
  callback_registration_required: '知乎登录回调尚未登记，暂不可用',
  credentials_required: '知乎登录配置尚未完成',
  identity_contract_required: '知乎账号识别配置待验证，暂不能登录',
  flow_expired: '本次登录已失效，请重新发起',
  state_missing: '授权回调缺少安全校验信息，未建立登录',
  state_mismatch: '授权校验失败，请重新登录',
  authorization_denied: '本次授权未完成，可以重新登录',
  code_missing: '授权未完成，请重新登录',
  upstream_failed: '知乎登录暂时不可用，请稍后重试',
  identity_invalid: '无法确认知乎账号身份，未建立登录',
  busy: '登录服务暂忙，请稍后重试',
};
const fail = code => { throw Object.assign(new Error(messages[code]), { code }); };

function keychain(service, account) {
  if (process.platform !== 'darwin') return Promise.resolve(null);
  return new Promise(resolve => execFile('/usr/bin/security',
    ['find-generic-password', '-s', service, '-a', account, '-w'], { timeout: 5000 },
    (error, stdout) => resolve(error ? null : stdout.trim())));
}

export async function readCredentials(config) {
  const appKey = process.env.ZHIHU_OAUTH_APP_KEY || await keychain(config.oauth.credentialService, config.oauth.credentialAccount);
  return { appKey };
}

export function publicCallback(value) {
  try {
    const url = new URL(value);
    const host = url.hostname;
    return url.protocol === 'https:' && !url.username && !url.password && !url.search && !url.hash
      && url.pathname === '/auth/callback' && host.includes('.') && !isIP(host)
      && !host.includes(':') && !host.startsWith('[')
      && !/\.(localhost|local|internal|test|invalid)$/.test(host) && host !== 'localhost';
  } catch { return false; }
}

function identityConfigured(config) {
  // Official user_info PDF supplied 2026-09-15 documents a top-level uid.
  return JSON.stringify(config.oauth.identityPath) === '["uid"]';
}

export function profileFromUser(profile) {
  const uid = profile?.uid;
  const subject = Number.isSafeInteger(uid) && uid > 0 ? String(uid) : uid;
  if (typeof subject !== 'string' || !/^[1-9][0-9]{0,19}$/.test(subject)) fail('identity_invalid');
  const nickname = typeof profile.fullname === 'string' ? profile.fullname.replace(/[\u0000-\u001f\u007f]/g, '').trim().slice(0, 80) : '';
  let avatarUrl;
  try {
    const url = new URL(profile.avatar_path);
    if (url.protocol === 'https:' && !url.username && !url.password && !url.port
      && url.hostname.endsWith('.zhimg.com') && url.href.length <= 2048) avatarUrl = url.href;
  } catch { /* Missing or untrusted avatar uses the existing neutral placeholder. */ }
  return { subject, profile: { provider: 'zhihu', nickname: nickname || '知乎用户', ...(avatarUrl ? { avatarUrl } : {}) } };
}

export function parseProviderJSON(text) {
  // Preserve int64 user IDs before JS rounds them. Older runtimes fail closed
  // on unsafe numeric IDs in profileFromUser instead of merging two accounts.
  return JSON.parse(text, (key, value, context) => key === 'uid' && typeof value === 'number'
    && context?.source ? context.source : value);
}

async function requestJSON(url, init) {
  try {
    const response = await fetch(url, { ...init, redirect: 'error', signal: AbortSignal.timeout(15000) });
    if (!response.ok) fail('upstream_failed');
    const chunks = [];
    let bytes = 0;
    for await (const chunk of response.body) {
      bytes += chunk.length;
      if (bytes > 1_000_000) fail('upstream_failed');
      chunks.push(Buffer.from(chunk));
    }
    return parseProviderJSON(Buffer.concat(chunks).toString('utf8'));
  } catch { fail('upstream_failed'); }
}

export function createLogin(config, { credentials = () => readCredentials(config), request = requestJSON, now = Date.now } = {}) {
  const flows = new Map();
  function clean() {
    for (const [id, flow] of flows) if (flow.expires <= now()) flows.delete(id);
  }
  async function status() {
    let code = null;
    if (!config.oauth.enabled || !publicCallback(config.oauth.redirectUri)) code = 'deployment_required';
    else {
      const creds = await credentials();
      if (!creds.appKey) code = 'credentials_required';
      else if (!identityConfigured(config)) code = 'identity_contract_required';
      else if (config.oauth.callbackRegistered !== true) code = 'callback_registration_required';
    }
    return { ready: !code, code, message: code ? messages[code] : '使用知乎账号登录，保存你的梦境' };
  }
  async function start() {
    const state = await status();
    if (!state.ready) fail(state.code);
    clean();
    if (flows.size >= 1000) fail('busy');
    const flowId = randomBytes(32).toString('base64url');
    const nonce = randomBytes(32).toString('base64url');
    flows.set(flowId, { state: nonce, expires: now() + 600000 });
    const url = new URL('https://openapi.zhihu.com/authorize');
    url.search = new URLSearchParams({ app_id: config.oauth.appId, redirect_uri: config.oauth.redirectUri, response_type: 'code', state: nonce });
    return { flow_id: flowId, authorization_url: url.toString() };
  }
  async function callback(input) {
    clean();
    const flow = flows.get(input.flow_id);
    flows.delete(input.flow_id); // One attempt only, including failed/parallel callbacks.
    if (!flow) fail('flow_expired');
    if (input.error) fail('authorization_denied');
    if (!input.state) fail('state_missing');
    const a = Buffer.from(String(input.state)), b = Buffer.from(flow.state);
    if (a.length !== b.length || !timingSafeEqual(a, b)) fail('state_mismatch');
    const code = input.authorization_code || input.code;
    if (typeof code !== 'string' || !code || code.length > 4096) fail('code_missing');
    const state = await status();
    if (!state.ready) fail(state.code);
    const { appKey } = await credentials();
    let token;
    try {
      const payload = await request('https://openapi.zhihu.com/access_token', {
        method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: new URLSearchParams({ app_id: config.oauth.appId, app_key: appKey, grant_type: 'authorization_code', redirect_uri: config.oauth.redirectUri, code }).toString(),
      });
      const tokenCode = payload?.code ?? payload?.Code;
      if (tokenCode !== undefined && ![0, 20000].includes(tokenCode)) fail('upstream_failed');
      const result = payload?.access_token ? payload : payload?.data?.access_token ? payload.data : payload?.Data;
      token = result?.access_token;
      const expires = Number(result?.expires_in);
      if (typeof token !== 'string' || !token || /[\r\n]/.test(token)
        || !Number.isFinite(expires) || expires <= 0) fail('upstream_failed');
      const profile = await request('https://openapi.zhihu.com/user', {
        // OAuth /user uses the user's token directly, unlike developer data APIs.
        method: 'GET', headers: { Authorization: `Bearer ${token}` },
      });
      const businessCode = profile?.code ?? profile?.Code;
      if (businessCode !== undefined && ![0, 20000].includes(businessCode)) fail('identity_invalid');
      const identity = profileFromUser(profile);
      return { provider: 'zhihu', ...identity, verified: true, session_seconds: Math.min(Math.floor(expires), 86400) };
    } catch (error) {
      if (error?.code === 'identity_invalid') fail('identity_invalid');
      fail('upstream_failed'); // Never expose upstream response bodies or credentials.
    } finally { token = null; }
  }
  return { status, start, callback };
}
