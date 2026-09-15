"""Same-origin bridge to a private Node OAuth adapter; no provider secrets here."""
import re
from urllib.parse import urlsplit

import httpx
from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse

from app.services.invite_auth import COOKIE

FLOW_COOKIE = "dreamcard_zhihu_flow"
MESSAGES = {
    "deployment_required": "知乎登录等待部署并配置公网回调，本地暂不可用",
    "callback_registration_required": "知乎登录回调尚未登记，暂不可用",
    "credentials_required": "知乎登录配置尚未完成",
    "identity_contract_required": "知乎账号识别配置待验证，暂不能登录",
    "flow_expired": "本次登录已失效，请重新发起",
    "state_missing": "授权回调缺少安全校验信息，未建立登录",
    "state_mismatch": "授权校验失败，请重新登录",
    "authorization_denied": "本次授权未完成，可以重新登录",
    "code_missing": "授权未完成，请重新登录",
    "upstream_failed": "知乎登录暂时不可用，请稍后重试",
    "identity_invalid": "无法确认知乎账号身份，未建立登录",
    "busy": "登录服务暂忙，请稍后重试",
    "unavailable": "知乎登录服务暂未连接，你仍可使用邀请码登录",
}


class ZhihuBridge:
    async def call(self, action: str, body: dict | None = None):
        # Fixed loopback destination, no credentials, user-supplied URLs or redirects.
        async with httpx.AsyncClient(timeout=40, trust_env=False, follow_redirects=False) as client:
            url = f"http://127.0.0.1:4173/api/login/{action}"
            result = await (client.get(url) if body is None else client.post(url, json=body))
        if result.status_code not in (200, 400) or len(result.content) > 16384:
            raise ValueError("invalid broker response")
        data = result.json()
        if not isinstance(data, dict):
            raise ValueError("invalid broker response")
        return data


def install_zhihu_auth(app, settings):
    app.state.zhihu_bridge = ZhihuBridge()
    secure = settings.environment == "production"

    async def call(action, body=None):
        try:
            return await app.state.zhihu_bridge.call(action, body)
        except (httpx.HTTPError, ValueError, TypeError):
            return {"code": "unavailable"}

    def error(data):
        code = data.get("code")
        if code not in MESSAGES:
            code = "unavailable"
        return code, MESSAGES[code]

    @app.get("/api/v1/auth/zhihu/status")
    async def status():
        data = await call("status")
        if data.get("ready") is True:
            return {"ready": True, "code": None, "message": "使用知乎账号登录，保存你的梦境"}
        code, message = error(data)
        return {"ready": False, "code": code, "message": message}

    @app.post("/api/v1/auth/zhihu/start")
    async def start(request: Request):
        data = await call("start", {})
        url = data.get("authorization_url", "")
        flow = data.get("flow_id", "")
        parsed = urlsplit(url) if isinstance(url, str) else urlsplit("")
        if (parsed.scheme != "https" or parsed.netloc != "openapi.zhihu.com"
                or parsed.path != "/authorize" or parsed.fragment
                or not isinstance(flow, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", flow)):
            code, message = error(data)
            return JSONResponse({"error": {"code": code, "message": message}}, status_code=503)
        response = JSONResponse({"authorization_url": url})
        response.set_cookie(FLOW_COOKIE, flow, max_age=600, httponly=True, secure=secure, samesite="lax", path="/auth/callback")
        return response

    @app.get("/auth/callback")
    async def callback(request: Request):
        flow = request.cookies.get(FLOW_COOKIE, "")
        code = "flow_expired"
        token = None
        ttl = 0
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", flow):
            fields = ("authorization_code", "code", "state", "error")
            query = request.query_params
            if all(len(query.getlist(key)) <= 1 and len(query.get(key, "")) <= 4096 for key in fields):
                data = await call("callback", {"flow_id": flow, **{key: query.get(key, "") for key in fields}})
                subject = data.get("subject")
                ttl = data.get("session_seconds")
                if (data.get("verified") is True and data.get("provider") == "zhihu"
                        and isinstance(subject, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,256}", subject)
                        and type(ttl) is int and 0 < ttl <= 86400):
                    result = app.state.invite_auth.login_external("zhihu", subject, request.cookies.get(COOKIE), ttl, data.get("profile"))
                    if result:
                        _, token = result
                        code = "success"
                    else:
                        code = "identity_invalid"
                else:
                    code, _ = error(data)
        # Strip authorization code/state from the return URL, never trust a return_to URL.
        response = RedirectResponse(f"/?zhihu={code}#invite", status_code=303,
                                    headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        response.delete_cookie(FLOW_COOKIE, path="/auth/callback", secure=secure, httponly=True, samesite="lax")
        if token:
            response.set_cookie(COOKIE, token, max_age=ttl, httponly=True, secure=secure, samesite="lax", path="/")
        return response
