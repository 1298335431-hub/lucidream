"""Opaque HttpOnly sessions; invite and session secrets are never stored raw."""
import hashlib
import json
import secrets
import sqlite3
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

COOKIE = "dreamcard_session"


def new_invite_code() -> str:
    alphabet = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    value = "".join(secrets.choice(alphabet) for _ in range(12))
    return "-".join(value[i:i + 4] for i in range(0, 12, 4))


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class InviteLogin(BaseModel):
    invite_code: str = Field(min_length=1, max_length=100)


class InviteAuth:
    def __init__(self, path: Path, quota_total: int = 8):
        self.path = path
        self.quota_total = quota_total
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS invite_accounts (
                    id TEXT PRIMARY KEY, code_hash TEXT UNIQUE NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, created_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    token_hash TEXT PRIMARY KEY, account_id TEXT NOT NULL,
                    expires_at REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS auth_attempts (
                    client_hash TEXT PRIMARY KEY, window_start REAL NOT NULL, attempts INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS external_identities (
                    provider TEXT NOT NULL, subject_hash TEXT NOT NULL, account_id TEXT NOT NULL,
                    PRIMARY KEY(provider, subject_hash));
                CREATE TABLE IF NOT EXISTS account_profiles (
                    account_id TEXT PRIMARY KEY, nickname TEXT NOT NULL, avatar_url TEXT);
                CREATE TABLE IF NOT EXISTS image_quota_usage (
                    account_id TEXT NOT NULL, session_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    created_at REAL NOT NULL, PRIMARY KEY(account_id, session_id, revision));
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def issue(self):
        code = new_invite_code()
        account = secrets.token_hex(16)
        with self.connect() as db:
            db.execute("INSERT INTO invite_accounts(id, code_hash, created_at) VALUES(?,?,?)", (account, digest(code), time.time()))
        return account, code

    def quota(self, account: str):
        with self.connect() as db:
            used = db.execute("SELECT COUNT(*) FROM image_quota_usage WHERE account_id=?", (account,)).fetchone()[0]
        return {"total": self.quota_total, "used": used, "remaining": max(0, self.quota_total - used)}

    def reserve_image(self, account: str, session_id: str, revision: int) -> bool:
        # Durable ledger deliberately survives dream deletion. Serialize competing requests.
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM image_quota_usage WHERE account_id=? AND session_id=? AND revision=?", (account, session_id, revision)).fetchone():
                return True
            if db.execute("SELECT COUNT(*) FROM image_quota_usage WHERE account_id=?", (account,)).fetchone()[0] >= self.quota_total:
                return False
            db.execute("INSERT INTO image_quota_usage VALUES(?,?,?,?)", (account, session_id, revision, time.time()))
        return True

    def login(self, code: str, previous: str | None):
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            account = db.execute("SELECT id FROM invite_accounts WHERE code_hash=? AND enabled=1", (digest(code.strip().upper()),)).fetchone()
            if account is None:
                return None
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
            if previous:
                db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(previous),))
            db.execute("INSERT INTO auth_sessions VALUES(?,?,?)", (digest(token), account[0], now + 604800))
        return account[0], token

    def login_external(self, provider: str, subject: str, previous: str | None, ttl: int, profile: dict | None = None):
        """Only called with server-verified identity; never merge an existing invite account."""
        if provider != "zhihu" or not subject or not 0 < ttl <= 86400:
            return None
        now = time.time()
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT account_id FROM external_identities WHERE provider=? AND subject_hash=?", (provider, digest(subject))).fetchone()
            if row:
                account = row[0]
                if not db.execute("SELECT 1 FROM invite_accounts WHERE id=? AND enabled=1", (account,)).fetchone():
                    return None
            else:
                account = secrets.token_hex(16)
                # Legacy table also holds account ownership. No usable invite is issued.
                db.execute("INSERT INTO invite_accounts(id, code_hash, created_at) VALUES(?,?,?)", (account, digest(secrets.token_urlsafe(64)), now))
                db.execute("INSERT INTO external_identities VALUES(?,?,?)", (provider, digest(subject), account))
            token = secrets.token_urlsafe(32)
            db.execute("DELETE FROM auth_sessions WHERE expires_at < ?", (now,))
            if previous:
                db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(previous),))
            db.execute("INSERT INTO auth_sessions VALUES(?,?,?)", (digest(token), account, now + ttl))
            profile = profile if isinstance(profile, dict) else {}
            nickname = profile.get("nickname")
            nickname = "".join(c for c in nickname if c.isprintable()).strip()[:80] if isinstance(nickname, str) else ""
            avatar = profile.get("avatarUrl")
            try:
                url = urlsplit(avatar) if isinstance(avatar, str) and len(avatar) <= 2048 else None
                if not (url and url.scheme == "https" and (url.hostname or "").endswith(".zhimg.com")
                        and not url.username and not url.password and not url.port):
                    avatar = None
            except ValueError:
                avatar = None
            db.execute("INSERT INTO account_profiles VALUES(?,?,?) ON CONFLICT(account_id) DO UPDATE SET nickname=excluded.nickname, avatar_url=excluded.avatar_url",
                       (account, nickname or "知乎用户", avatar))
        return account, token

    def profile(self, account: str):
        with self.connect() as db:
            row = db.execute("SELECT nickname, avatar_url FROM account_profiles WHERE account_id=?", (account,)).fetchone()
        if row:
            return {"provider": "zhihu", "nickname": row[0], **({"avatarUrl": row[1]} if row[1] else {})}
        return None

    def account(self, token: str | None):
        if not token or len(token) > 128:
            return None
        with self.connect() as db:
            row = db.execute("SELECT a.id FROM auth_sessions s JOIN invite_accounts a ON a.id=s.account_id WHERE s.token_hash=? AND s.expires_at>? AND a.enabled=1", (digest(token), time.time())).fetchone()
        return row[0] if row else None

    def revoke(self, token: str | None):
        if token:
            with self.connect() as db:
                db.execute("DELETE FROM auth_sessions WHERE token_hash=?", (digest(token),))


def install_invite_auth(app, settings):
    auth = InviteAuth(settings.database_path, settings.image_quota_total)
    app.state.invite_auth = auth

    def error(status, code, message):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers={"Cache-Control": "no-store"})

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        request.state.account_id = None
        if path.startswith("/api/") and request.method != "OPTIONS":
            if request.method not in ("GET", "HEAD"):
                origin = request.headers.get("origin")
                if origin and origin not in settings.parsed_cors_origins():
                    return error(403, "origin_denied", "请求来源不受信任")
            if settings.auth_enabled:
                public = {"/api/v1/health", "/api/v1/auth/login", "/api/v1/auth/logout",
                          "/api/v1/auth/zhihu/status", "/api/v1/auth/zhihu/start"}
                account = auth.account(request.cookies.get(COOKIE))
                request.state.account_id = account
                if path not in public and not account:
                    return error(401, "authentication_required", "登录已失效，请重新登录")
                if path.startswith("/api/v1/dreams/") and path != "/api/v1/dreams/extract":
                    session_id = path.split("/")[4]
                    with auth.connect() as db:
                        owned = db.execute("SELECT 1 FROM dream_sessions WHERE id=? AND owner_id=?", (session_id, account)).fetchone()
                    if not owned:
                        return error(404, "not_found", "没有找到这次梦境记录")
        response = await call_next(request)
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.post("/api/v1/auth/login")
    def login(payload: InviteLogin, request: Request):
        result = auth.login(payload.invite_code, request.cookies.get(COOKIE))
        if not result:
            return error(401, "invalid_invite", "邀请码无效或已停用")
        account, token = result
        response = JSONResponse({"account_id": account})
        response.set_cookie(COOKIE, token, max_age=604800, httponly=True,
                            secure=settings.environment == "production", samesite="lax", path="/")
        return response

    @app.get("/api/v1/auth/me")
    def me(request: Request):
        if not request.state.account_id:
            return error(401, "authentication_required", "请先登录")
        profile = auth.profile(request.state.account_id)
        return {"account_id": request.state.account_id, **({"profile": profile} if profile else {})}

    @app.post("/api/v1/auth/logout")
    def logout(request: Request):
        auth.revoke(request.cookies.get(COOKIE))
        response = JSONResponse({"logged_out": True})
        response.delete_cookie(COOKIE, path="/", secure=settings.environment == "production", httponly=True, samesite="lax")
        return response

    @app.get("/api/v1/account/quota")
    def account_quota(request: Request):
        if not request.state.account_id:
            return error(401, "authentication_required", "请先登录")
        return auth.quota(request.state.account_id)

    @app.get("/api/v1/dreams")
    def my_dreams(request: Request, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100), q: str = Query("", max_length=300)):
        with auth.connect() as db:
            source = """FROM dream_sessions d
                LEFT JOIN interpretation_generations i ON i.session_id=d.id AND i.revision=d.revision
                LEFT JOIN image_generations g ON g.session_id=d.id AND g.revision=d.revision
                WHERE d.owner_id=? AND (?='' OR instr(d.dream_text, ?) > 0 OR instr(coalesce(i.result_json,''), ?) > 0)"""
            params = (request.state.account_id, q.strip(), q.strip(), q.strip())
            total = db.execute("SELECT count(*) " + source, params).fetchone()[0]
            rows = db.execute("""SELECT d.id, d.status, d.revision, d.created_at, d.updated_at, d.dream_text,
                d.symbols_json, i.status AS interpretation_status, i.result_json,
                g.status AS image_status, (g.image_url IS NOT NULL OR EXISTS (
                  SELECT 1 FROM image_assets a WHERE a.session_id=d.id AND a.revision=d.revision
                )) AS has_image """ + source + " ORDER BY d.created_at DESC, d.id DESC LIMIT ? OFFSET ?", (*params, limit, offset)).fetchall()
        dreams = []
        for row in rows:
            item = dict(row)
            raw_result = item.pop("result_json")
            raw_symbols = item.pop("symbols_json")
            try:
                result = json.loads(raw_result or "{}")
                title = result.get("interpretation", {}).get("title", "")
                item["title"] = title if isinstance(title, str) and title.strip() else item["dream_text"][:28]
            except (ValueError, TypeError, AttributeError):
                item["title"] = item["dream_text"][:28]
            try:
                symbols = json.loads(raw_symbols)
                item["tags"] = [value for key in ("scenes", "characters", "objects") for value in symbols.get(key, []) if isinstance(value, str)][:5]
            except (ValueError, TypeError, AttributeError):
                item["tags"] = []
            item["has_image"] = bool(item["has_image"])
            dreams.append(item)
        return {"dreams": dreams, "total": total, "next_offset": offset + len(dreams) if offset + len(dreams) < total else None}
