import http from 'node:http';
import { existsSync } from 'node:fs';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createOAuth } from './lib/oauth.mjs';
import { createLogin, messages as loginMessages } from './lib/login.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
const config = JSON.parse(await readFile(path.join(root, 'hackathon.config.json'), 'utf8'));
const publicDir = path.join(root, 'public');
const oauth = createOAuth(config);
const login = createLogin(config);
// Private companion service. Only expose the FastAPI routes through the public proxy.
const runtimeHost = '127.0.0.1';
const runtimePort = Number(process.env.PORT || config.port);
const types = new Map([['.html', 'text/html; charset=utf-8'], ['.css', 'text/css; charset=utf-8'], ['.js', 'text/javascript; charset=utf-8']]);

function headers(type = 'application/json; charset=utf-8') {
  return {
    'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Content-Security-Policy': "default-src 'self'; img-src 'self' https: data:; style-src 'self'; script-src 'self'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
  };
}
function json(response, status, payload) { response.writeHead(status, headers()); response.end(JSON.stringify(payload)); }
function redirect(response, location) { response.writeHead(302, { Location: location, 'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer' }); response.end(); }

const server = http.createServer(async (request, response) => {
  const url = new URL(request.url, `http://${config.host}:${config.port}`);
  try {
    if (url.pathname.startsWith('/api/login/')) {
      // Application bridge does not accept browser-originated cross-site requests.
      if (request.headers.origin) return json(response, 403, { code: 'origin_denied' });
      try {
        if (request.method === 'GET' && url.pathname === '/api/login/status') return json(response, 200, await login.status());
        if (request.method !== 'POST' || !['/api/login/start', '/api/login/callback'].includes(url.pathname)) return json(response, 404, { code: 'not_found' });
        let body = '';
        for await (const chunk of request) {
          body += chunk.toString();
          if (body.length > 16384) return json(response, 413, { code: 'invalid_request' });
        }
        const input = JSON.parse(body || '{}');
        if (!input || typeof input !== 'object' || Array.isArray(input)) return json(response, 400, { code: 'invalid_request' });
        return json(response, 200, url.pathname.endsWith('/start') ? await login.start() : await login.callback(input));
      } catch (error) {
        const code = Object.hasOwn(loginMessages, error?.code || '') ? error.code : 'upstream_failed';
        return json(response, 400, { code, message: loginMessages[code] });
      }
    }
    if (request.method === 'GET' && url.pathname === '/api/health') return json(response, 200, { ok: true, project: config.projectName, oauthEnabled: true });
    if (request.method === 'GET' && url.pathname === '/api/oauth/status') return json(response, 200, { ok: true, ...(await oauth.status(request, response)) });
    if (request.method === 'GET' && url.pathname === '/api/oauth/start') {
      try { return redirect(response, await oauth.start(request, response)); }
      catch (error) { oauth.record(request, response, error); return redirect(response, '/?oauth=error'); }
    }
    if (request.method === 'GET' && url.pathname === '/auth/callback') {
      try { await oauth.callback(request, response, url); return redirect(response, '/?oauth=success'); }
      catch (error) { oauth.record(request, response, error); return redirect(response, '/?oauth=error'); }
    }
    if (request.method === 'POST' && url.pathname === '/api/oauth/run-all') return json(response, 200, { ok: true, results: await oauth.runAll(request, response) });
    if (request.method === 'POST' && url.pathname === '/api/oauth/logout') { oauth.logout(request, response); return json(response, 200, { ok: true }); }
    if (request.method !== 'GET') return json(response, 405, { ok: false, error: { message: '不支持的请求方法' } });
    const requested = url.pathname === '/' ? '/index.html' : url.pathname;
    const filePath = path.join(publicDir, path.normalize(requested));
    if (!filePath.startsWith(publicDir) || !existsSync(filePath)) return json(response, 404, { ok: false, error: { message: '页面不存在' } });
    response.writeHead(200, headers(types.get(path.extname(filePath)) || 'application/octet-stream'));
    response.end(await readFile(filePath));
  } catch (error) { json(response, 401, { ok: false, error: { code: error.code || 'REQUEST_FAILED', message: error.message } }); }
});

server.listen(runtimePort, runtimeHost, () => process.stdout.write(`${config.projectName}: http://${runtimeHost}:${runtimePort}/\n`));
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => server.close(() => process.exit(0)));
