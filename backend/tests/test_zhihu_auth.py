import httpx
import pytest
from fastapi.testclient import TestClient
from app.core.config import Settings
from app.main import create_app
from app.services.invite_auth import COOKIE
from app.services.zhihu_auth import FLOW_COOKIE


class Broker:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.result = {"provider": "zhihu", "subject": "fictional-id", "verified": True, "session_seconds": 3600}

    async def call(self, action, body=None):
        self.calls.append((action, body))
        if self.fail:
            raise httpx.ConnectError("private details")
        if action == "status":
            return {"ready": False, "code": "deployment_required", "message": "ignored upstream text", "secret": "do not expose"}
        if action == "start":
            return {"flow_id": "A" * 43, "authorization_url": "https://openapi.zhihu.com/authorize?state=test"}
        return self.result


def setup(tmp_path):
    settings = Settings(_env_file=None, DREAMCARD_ENV="test", DREAMCARD_AUTH_ENABLED=True,
                        DREAMCARD_MODEL_MODE="mock", DREAMCARD_DATABASE_PATH=tmp_path / "oauth.db")
    app = create_app(settings=settings)
    app.state.zhihu_bridge = Broker()
    return app, TestClient(app)


def callback(client, **params):
    client.post('/api/v1/auth/zhihu/start')
    return client.get('/auth/callback', params={"authorization_code": "test-code", "state": "test", **params}, follow_redirects=False)


def test_status_public_but_no_sensitive_configuration(tmp_path):
    app, client = setup(tmp_path)
    result = client.get('/api/v1/auth/zhihu/status')
    assert result.status_code == 200
    assert result.json()['code'] == 'deployment_required'
    assert 'secret' not in result.text and 'ignored upstream' not in result.text
    assert result.headers['cache-control'] == 'no-store'
    assert client.get('/api/v1/dreams').status_code == 401


def test_broker_offline_is_clear_and_does_not_block_invites(tmp_path):
    app, client = setup(tmp_path)
    app.state.zhihu_bridge.fail = True
    assert client.get('/api/v1/auth/zhihu/status').json()['code'] == 'unavailable'
    assert client.post('/api/v1/auth/zhihu/start').status_code == 503
    account, invite = app.state.invite_auth.issue()
    assert client.post('/api/v1/auth/login', json={"invite_code": invite}).json()['account_id'] == account


def test_start_blocks_foreign_origins_and_binds_callback_cookie(tmp_path):
    app, client = setup(tmp_path)
    assert client.post('/api/v1/auth/zhihu/start', headers={'origin': 'https://evil.example'}).status_code == 403
    assert not app.state.zhihu_bridge.calls
    result = client.post('/api/v1/auth/zhihu/start')
    assert 'flow_id' not in result.text
    assert 'HttpOnly' in result.headers['set-cookie'] and 'SameSite=lax' in result.headers['set-cookie']
    assert 'Path=/auth/callback' in result.headers['set-cookie']


def test_callback_requires_cookie_and_cleans_query(tmp_path):
    app, client = setup(tmp_path)
    response = client.get('/auth/callback?authorization_code=do-not-leak&state=wrong&return_to=https://evil.example', follow_redirects=False)
    assert response.headers['location'] == '/?zhihu=flow_expired#invite'
    assert 'do-not-leak' not in response.text
    assert response.headers['referrer-policy'] == 'no-referrer'
    assert not app.state.zhihu_bridge.calls
    assert client.get('/api/v1/auth/me').status_code == 401


def test_verified_account_persists_and_never_merges_invite_history(tmp_path):
    app, client = setup(tmp_path)
    old_account, invite = app.state.invite_auth.issue()
    client.post('/api/v1/auth/login', json={"invite_code": invite})
    old_token = client.cookies.get(COOKIE)
    old_dream = client.post('/api/v1/dreams/extract', json={'dream_text': '我走进一座森林'}).json()['id']
    result = callback(client)
    assert result.headers['location'] == '/?zhihu=success#invite'
    assert not client.cookies.get(FLOW_COOKIE)
    new_account = client.get('/api/v1/auth/me').json()['account_id']
    assert new_account != old_account
    assert app.state.invite_auth.account(old_token) is None
    assert client.get('/api/v1/dreams/' + old_dream).status_code == 404
    assert client.get('/api/v1/account/quota').json()['remaining'] == 8
    app.state.invite_auth.reserve_image(new_account, 'test-dream', 1)
    client.post('/api/v1/auth/logout')
    assert client.get('/api/v1/auth/me').status_code == 401
    callback(client)
    assert client.get('/api/v1/auth/me').json()['account_id'] == new_account
    assert client.get('/api/v1/account/quota').json()['remaining'] == 7
    client.post('/api/v1/auth/login', json={"invite_code": invite})
    assert client.get('/api/v1/dreams/' + old_dream).status_code == 200


@pytest.mark.parametrize('result', [
    {"code": "state_missing"}, {"code": "state_mismatch"}, {"code": "identity_invalid"},
    {"provider": "zhihu", "subject": "id", "verified": False, "session_seconds": 3600},
    {"provider": "zhihu", "subject": "id", "verified": True, "session_seconds": 0},
    {"provider": "other", "subject": "id", "verified": True, "session_seconds": 3600},
])
def test_failed_identity_never_creates_a_session(tmp_path, result):
    app, client = setup(tmp_path)
    app.state.zhihu_bridge.result = result
    response = callback(client)
    assert 'success' not in response.headers['location']
    assert not client.cookies.get(COOKIE)
    assert client.get('/api/v1/auth/me').status_code == 401


def test_disabled_external_account_stays_disabled(tmp_path):
    app, client = setup(tmp_path)
    callback(client)
    account = client.get('/api/v1/auth/me').json()['account_id']
    with app.state.invite_auth.connect() as db:
        db.execute('UPDATE invite_accounts SET enabled=0 WHERE id=?', (account,))
    assert 'success' not in callback(client).headers['location']
    assert client.get('/api/v1/auth/me').status_code == 401


def test_profile_reaches_me_without_contact_details_or_tokens(tmp_path):
    app, client = setup(tmp_path)
    app.state.zhihu_bridge.result['profile'] = {'nickname': '看山测试', 'avatarUrl': 'https://picx.zhimg.com/example.jpg', 'email': 'private@example.com', 'access_token': 'secret'}
    callback(client)
    result = client.get('/api/v1/auth/me')
    assert result.json()['profile'] == {'provider': 'zhihu', 'nickname': '看山测试', 'avatarUrl': 'https://picx.zhimg.com/example.jpg'}
    assert 'private' not in result.text and 'secret' not in result.text
    app.state.zhihu_bridge.result['profile'] = {'nickname': '新昵称', 'avatarUrl': 'https://evil.example/avatar'}
    callback(client)
    assert client.get('/api/v1/auth/me').json()['profile'] == {'provider': 'zhihu', 'nickname': '新昵称'}
    _, invite = app.state.invite_auth.issue()
    client.post('/api/v1/auth/login', json={'invite_code': invite})
    assert 'profile' not in client.get('/api/v1/auth/me').json()


def test_callback_registration_status_is_preserved(tmp_path):
    app, client = setup(tmp_path)
    class PendingBroker:
        async def call(self, action, body=None):
            return {'code': 'callback_registration_required', 'ready': False}
    app.state.zhihu_bridge = PendingBroker()
    assert client.get('/api/v1/auth/zhihu/status').json()['code'] == 'callback_registration_required'
