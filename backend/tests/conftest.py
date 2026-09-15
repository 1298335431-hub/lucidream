import pytest


@pytest.fixture(autouse=True)
def isolated_test_auth(monkeypatch):
    monkeypatch.setenv("DREAMCARD_ENV", "test")
    monkeypatch.setenv("DREAMCARD_AUTH_ENABLED", "false")
