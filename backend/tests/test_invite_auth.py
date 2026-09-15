import time
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from app.schemas.dream import DreamSymbols
from app.services.invite_auth import COOKIE, digest
from app.storage.repository import DreamRepository


def test_new_invites_are_readable_short_codes(tmp_path):
    import re
    _, auth, _ = setup(tmp_path)
    account, code = auth.issue()
    assert re.fullmatch(r"[2-9A-HJ-NP-Z]{4}(-[2-9A-HJ-NP-Z]{4}){2}", code)
    result = auth.login(code.lower(), None)
    assert result and result[0] == account


def test_quota_is_atomic_durable_and_account_scoped(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from app.services.invite_auth import InviteAuth
    _, auth, _ = setup(tmp_path)
    account, _ = auth.issue()
    other, _ = auth.issue()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda i: auth.reserve_image(account, str(i), 1), range(20)))
    assert sum(results) == 8
    assert auth.quota(other)['remaining'] == 8
    assert InviteAuth(auth.path).quota(account)['remaining'] == 0
    accepted = str(results.index(True))
    assert auth.reserve_image(account, accepted, 1)
    assert not auth.reserve_image(account, accepted, 2)
    assert auth.quota(account)['used'] == 8


def setup(tmp_path):
    settings = Settings(_env_file=None, DREAMCARD_ENV="test", DREAMCARD_MODEL_MODE="mock", DREAMCARD_AUTH_ENABLED=True, DREAMCARD_DATABASE_PATH=tmp_path / "auth.db", DREAMCARD_MODERATION_MODE="disabled")
    app = create_app(settings=settings)
    return app, app.state.invite_auth, DreamRepository(settings.database_path)


def test_login_restore_logout_and_hash_storage(tmp_path):
    app, auth, repo = setup(tmp_path)
    account, code = auth.issue()
    client = TestClient(app)
    assert client.get("/api/v1/auth/me").status_code == 401
    response = client.post("/api/v1/auth/login", json={"invite_code": code.lower()})
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    token = client.cookies.get(COOKIE)
    assert client.get("/api/v1/auth/me").json()["account_id"] == account
    created = client.post("/api/v1/dreams/extract", json={"dream_text": "我在森林里开心地走路"}).json()
    assert client.get(f"/api/v1/dreams/{created['id']}").status_code == 200
    assert client.get("/api/v1/dreams").json()["dreams"][0]["id"] == created["id"]
    with auth.connect() as db:
        assert db.execute("SELECT code_hash FROM invite_accounts").fetchone()[0] == digest(code)
        assert db.execute("SELECT token_hash FROM auth_sessions").fetchone()[0] == digest(token)
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert auth.account(token) is None
    client.cookies.set(COOKIE, token)
    assert client.get(f"/api/v1/dreams/{created['id']}").status_code == 401
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"invite_code": code})
    assert client.get(f"/api/v1/dreams/{created['id']}").status_code == 200


@pytest.mark.parametrize("method,suffix", [("GET", ""), ("PUT", "/symbols"), ("DELETE", ""), ("GET", "/interpretation"), ("POST", "/interpretation"), ("GET", "/image"), ("POST", "/image"), ("POST", "/image/review"), ("GET", "/image/file")])
def test_other_accounts_and_legacy_records_are_inaccessible(tmp_path, method, suffix):
    app, auth, repo = setup(tmp_path)
    owner, _ = auth.issue()
    _, other_code = auth.issue()
    client = TestClient(app)
    client.post("/api/v1/auth/login", json={"invite_code": other_code})
    for account in (owner, None):
        record = repo.create("私密梦境", "reviewing_symbols", DreamSymbols(), None, "mock", owner_id=account)
        response = client.request(method, f"/api/v1/dreams/{record.id}{suffix}")
        assert response.status_code == 404
        assert "私密" not in response.text
        assert repo.get(record.id).dream_text == "私密梦境"
    assert client.get("/api/v1/dreams").json() == {"dreams": [], "total": 0, "next_offset": None}


def test_disabled_expired_rotated_and_fake_sessions(tmp_path):
    app, auth, repo = setup(tmp_path)
    account, code = auth.issue()
    client = TestClient(app)
    client.cookies.set(COOKIE, "true")
    assert client.get("/api/v1/dreams").status_code == 401
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"invite_code": code})
    old = client.cookies.get(COOKIE)
    client.post("/api/v1/auth/login", json={"invite_code": code})
    assert auth.account(old) is None
    with auth.connect() as db:
        db.execute("UPDATE auth_sessions SET expires_at=?", (time.time() - 1,))
    assert client.get("/api/v1/auth/me").status_code == 401
    client.post("/api/v1/auth/login", json={"invite_code": code})
    with auth.connect() as db:
        db.execute("UPDATE invite_accounts SET enabled=0 WHERE id=?", (account,))
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"invite_code": code}).status_code == 401


def test_origin_and_login_without_attempt_lockout(tmp_path):
    app, auth, repo = setup(tmp_path)
    client = TestClient(app)
    account, code = auth.issue()
    assert client.post("/api/v1/auth/login", json={"invite_code": code}, headers={"Origin": "https://evil.example"}).status_code == 403
    with auth.connect() as db:
        db.execute("INSERT INTO auth_attempts VALUES(?,?,?)", (digest('testclient'), time.time(), 100))
    for _ in range(12):
        assert client.post("/api/v1/auth/login", json={"invite_code": "wrong"}).status_code == 401
    for _ in range(12):
        assert client.post("/api/v1/auth/login", json={"invite_code": code}).status_code == 200
    assert client.get('/api/v1/auth/me').json()['account_id'] == account
    assert auth.quota(account) == {'total': 8, 'used': 0, 'remaining': 8}
    response = client.options("/api/v1/auth/login", headers={"Origin": "http://127.0.0.1:8443", "Access-Control-Request-Method": "POST"})
    assert response.headers["access-control-allow-credentials"] == "true"


def test_production_cannot_disable_auth():
    with pytest.raises(ValueError):
        Settings(_env_file=None, DREAMCARD_ENV="production", DREAMCARD_AUTH_ENABLED=False)


def test_archive_lists_only_current_account_with_saved_results_and_pagination(tmp_path):
    import json
    app, auth, repo = setup(tmp_path)
    owner, code = auth.issue()
    other, _ = auth.issue()
    client = TestClient(app)
    assert client.get('/api/v1/dreams').status_code == 401
    client.post('/api/v1/auth/login', json={'invite_code': code})
    first = repo.create('我在钟表店看见太阳', 'ready_to_generate', DreamSymbols(scenes=['钟表店']), None, 'mock', owner_id=owner)
    second = repo.create('一只狐狸', 'reviewing_symbols', DreamSymbols(), None, 'mock', owner_id=owner)
    repo.create('其他账户秘密', 'reviewing_symbols', DreamSymbols(), None, 'mock', owner_id=other)
    repo.begin_generation(first.id, first.revision)
    repo.complete_generation(first.id, first.revision, json.dumps({'interpretation': {'title': '结冰的太阳'}}, ensure_ascii=False))
    repo.save_image_asset(first.id, first.revision, 'https://example.com/asset.png', b'private-image', 'image/png')
    response = client.get('/api/v1/dreams?limit=1').json()
    assert response['total'] == 2 and response['next_offset'] == 1
    following = client.get('/api/v1/dreams?limit=1&offset=1').json()
    assert following['next_offset'] is None
    entries = response['dreams'] + following['dreams']
    assert {entry['id'] for entry in entries} == {first.id, second.id}
    generated = next(entry for entry in entries if entry['id'] == first.id)
    assert generated['title'] == '结冰的太阳'
    assert generated['has_image'] is True
    assert generated['tags'] == ['钟表店']
    assert generated['interpretation_status'] == 'completed'
    assert 'result_json' not in generated and 'private-image' not in str(entries)
    assert client.get('/api/v1/dreams', params={'q': '结冰'}).json()['total'] == 1
    assert client.get('/api/v1/dreams', params={'q': '其他账户秘密'}).json()['total'] == 0
    assert client.get('/api/v1/dreams?offset=-1').status_code == 422
    assert client.get('/api/v1/dreams?limit=101').status_code == 422
    assert auth.quota(owner)['used'] == 0


def test_archive_does_not_reuse_results_from_an_old_revision(tmp_path):
    import json
    app, auth, repo = setup(tmp_path)
    owner, code = auth.issue()
    dream = repo.create('当前记录', 'reviewing_symbols', DreamSymbols(), None, 'mock', owner_id=owner)
    repo.begin_generation(dream.id, dream.revision)
    repo.complete_generation(dream.id, dream.revision, json.dumps({'interpretation': {'title': '旧版本标题'}}))
    repo.save_image_asset(dream.id, dream.revision, 'https://example.com/old.png', b'old', 'image/png')
    with auth.connect() as db:
        db.execute('UPDATE dream_sessions SET revision=revision+1 WHERE id=?', (dream.id,))
    client = TestClient(app)
    client.post('/api/v1/auth/login', json={'invite_code': code})
    entry = client.get('/api/v1/dreams').json()['dreams'][0]
    assert entry['title'] == '当前记录'
    assert entry['interpretation_status'] is None and not entry['has_image']
