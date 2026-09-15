import json
import sqlite3
import stat

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.request_logging import install_request_logging
from app.schemas.dream import DreamSymbols
from app.services.invite_auth import InviteAuth
from app.storage.backup import snapshot_database
from app.storage.repository import DreamRepository


def data(tmp_path):
    path = tmp_path / "original.db"
    repo = DreamRepository(path)
    auth = InviteAuth(path)
    account, code = auth.issue()
    _, token = auth.login(code, None)
    dream = repo.create("私密梦境", "reviewing_symbols", DreamSymbols(), None, "mock", owner_id=account)
    auth.reserve_image(account, dream.id, 1)
    repo.save_image_asset(dream.id, 1, "https://example.com/image", b"original-image", "image/png")
    return path, repo, auth, account, code, token, dream


def test_upgrade_legacy_quota_keeps_usage_and_history(tmp_path):
    path, repo, auth, account, code, token, dream = data(tmp_path)
    old = InviteAuth(path, quota_total=5)
    for i in range(4):
        assert old.reserve_image(account, str(i), 1)
    assert old.quota(account)["remaining"] == 0
    current = InviteAuth(path)
    assert current.quota(account) == {"total": 8, "used": 5, "remaining": 3}
    assert current.account(token) == account
    assert repo.get(dream.id).dream_text == "私密梦境"
    assert current.reserve_image(account, dream.id, 1)
    assert current.quota(account)["used"] == 5
    for i in range(3):
        assert current.reserve_image(account, f"new-{i}", 1)
    assert not current.reserve_image(account, "ninth", 1)


def test_backup_and_restore_preserves_records_images_quota_but_revokes_sessions(tmp_path):
    path, repo, auth, account, code, token, dream = data(tmp_path)
    backup = tmp_path / "backup.db"
    snapshot_database(path, backup)
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
    restored = tmp_path / "restored.db"
    snapshot_database(backup, restored, restore=True)
    restored_repo, restored_auth = DreamRepository(restored), InviteAuth(restored)
    assert restored_repo.get(dream.id).dream_text == "私密梦境"
    assert restored_repo.get_image_asset(dream.id, 1, "https://example.com/image")["content"] == b"original-image"
    assert restored_auth.quota(account) == {"total": 8, "used": 1, "remaining": 7}
    assert restored_auth.account(token) is None
    assert restored_auth.login(code, None)[0] == account
    assert auth.account(token) == account  # Live source was not modified.


def test_snapshot_refuses_overwrite_missing_and_corrupt_source(tmp_path):
    path, *_ = data(tmp_path)
    before = path.read_bytes()
    with pytest.raises(FileExistsError):
        snapshot_database(path, path)
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        snapshot_database(tmp_path / "missing.db", tmp_path / "out.db")
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not a database")
    with pytest.raises(sqlite3.Error):
        snapshot_database(corrupt, tmp_path / "out.db", restore=True)
    assert not (tmp_path / "out.db").exists()
    assert not list(tmp_path.glob(".dreamcard-snapshot-*"))


def test_request_trace_never_logs_query_body_cookie_or_exception(caplog):
    app = FastAPI()
    @app.post("/test/{record_id}")
    def endpoint(record_id: str):
        raise RuntimeError("upstream-secret-private-dream")
    install_request_logging(app)
    response = TestClient(app).post("/test/private-record?code=private-code", headers={"Cookie": "token=private-cookie"}, json={"dream": "private-dream"})
    assert response.status_code == 500
    assert response.json()["error"]["trace_id"] == response.headers["X-Request-ID"]
    event = json.loads(caplog.records[-1].message)
    assert event["route"] == "/test/{record_id}"
    assert event["status"] == 500
    for secret in ("private-record", "private-code", "private-cookie", "private-dream", "upstream-secret"):
        assert secret not in caplog.text + response.text


def test_environment_typo_does_not_silently_disable_secure_cookie():
    with pytest.raises(ValueError):
        Settings(_env_file=None, DREAMCARD_ENV="prod", DREAMCARD_AUTH_ENABLED=True)


def test_quota_setting_validation():
    assert Settings(_env_file=None).image_quota_total == 8
    with pytest.raises(ValueError):
        Settings(_env_file=None, DREAMCARD_IMAGE_QUOTA_TOTAL=0)
