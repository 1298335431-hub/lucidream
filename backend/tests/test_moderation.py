import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from alibabacloud_green20220302.models import TextModerationPlusResponseBody

from app.core.config import Settings
from app.main import create_app
from app.services.moderation import TextModerator, ModerationError, ModerationDecision


def config(**kwargs):
    return Settings(_env_file=None, DREAMCARD_MODEL_MODE="mock",
                    DREAMCARD_MODERATION_MODE="aliyun", DREAMCARD_MODERATION_REGION="cn-shanghai",
                    ALIBABA_CLOUD_ACCESS_KEY_ID="fixture-id", ALIBABA_CLOUD_ACCESS_KEY_SECRET="fixture-secret", **kwargs)


class FakeClient:
    def __init__(self, payload=None, status=200, error=None):
        self.calls = []
        self.payload = payload if payload is not None else {"Code": 200, "Data": {"RiskLevel": "none"}}
        self.status = status
        self.error = error

    def text_moderation_plus_with_options(self, request, runtime):
        self.calls.append((request, runtime))
        if self.error:
            raise self.error
        body = TextModerationPlusResponseBody().from_map(self.payload)
        return SimpleNamespace(status_code=self.status, body=body)


@pytest.mark.parametrize("direction,service,limit", [("input", "llm_query_moderation", 2000), ("output", "llm_response_moderation", 5000)])
def test_sdk_contract(direction, service, limit):
    client = FakeClient()
    moderator = TextModerator(config(), client)
    assert moderator.check("梦" * limit, direction).allowed
    request, runtime = client.calls[0]
    assert request.service == service
    assert len(json.loads(request.service_parameters)["content"]) == limit
    assert runtime.autoretry is False and runtime.max_attempts == 1
    assert runtime.connect_timeout == runtime.read_timeout == 5000
    with pytest.raises(ModerationError, match="too_long"):
        moderator.check("梦" * (limit + 1), direction)
    assert len(client.calls) == 1


@pytest.mark.parametrize("risk", ["low", "medium", "high"])
def test_flagged_content_is_not_released(risk):
    moderator = TextModerator(config(), FakeClient({"Code": 200, "Data": {"RiskLevel": risk}}))
    with pytest.raises(ModerationError, match="content_review_required"):
        moderator.require_allowed("测试文本", "input")


@pytest.mark.parametrize("payload", [{}, {"Code": 408}, {"Code": 588}, {"Code": 200}, {"Code": 200, "Data": {"RiskLevel": "unexpected"}}])
def test_malformed_or_failed_response_never_passes(payload):
    client = FakeClient(payload)
    with pytest.raises(ModerationError):
        TextModerator(config(), client).check("测试文本", "input")
    assert len(client.calls) == 1


def test_exceptions_and_config_are_sanitized():
    client = FakeClient(error=TimeoutError("fixture-secret PRIVATE DREAM"))
    moderator = TextModerator(config(), client)
    with pytest.raises(ModerationError) as caught:
        moderator.check("PRIVATE DREAM", "input")
    assert str(caught.value) == "moderation_unavailable"
    assert len(client.calls) == 1
    assert "fixture-secret" not in repr(moderator.settings)
    assert "fixture-id" not in json.dumps(moderator.configuration())
    assert moderator.configuration()["live_connection_verified"] is False


def test_disabled_and_missing_config_do_not_call_provider():
    client = FakeClient()
    settings = Settings(_env_file=None)
    with pytest.raises(ModerationError, match="not_enabled"):
        TextModerator(settings, client).check("测试", "input")
    settings.moderation_mode = "aliyun"
    with pytest.raises(ModerationError, match="not_configured"):
        TextModerator(settings, client).check("测试", "input")
    assert client.calls == []


def test_input_and_output_gates_before_persistence(tmp_path, monkeypatch):
    calls = []
    def check(_self, text, direction):
        calls.append(direction)
        return ModerationDecision("none" if direction == "input" else "high", None)
    monkeypatch.setattr(TextModerator, "check", check)
    client = TestClient(create_app(config(DREAMCARD_DATABASE_PATH=tmp_path / "test.db")))
    response = client.post("/api/v1/dreams/extract", json={"dream_text": "我梦见森林"})
    assert response.status_code == 422
    assert calls == ["input", "output"]
    assert "id" not in response.json()


def test_input_unavailable_prevents_model_call(tmp_path, monkeypatch):
    from app.services.extractor import DreamExtractor
    def unavailable(*_args):
        raise ModerationError("moderation_unavailable")
    monkeypatch.setattr(TextModerator, "check", unavailable)
    monkeypatch.setattr(DreamExtractor, "extract", lambda *_: pytest.fail("must not call model"))
    client = TestClient(create_app(config(DREAMCARD_DATABASE_PATH=tmp_path / "test.db")))
    response = client.post("/api/v1/dreams/extract", json={"dream_text": "我梦见森林"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "moderation_unavailable"


def test_edit_rejection_preserves_revision(tmp_path, monkeypatch):
    monkeypatch.setattr(TextModerator, "check", lambda *_: ModerationDecision("none", None))
    client = TestClient(create_app(config(DREAMCARD_DATABASE_PATH=tmp_path / "test.db")))
    dream = client.post("/api/v1/dreams/extract", json={"dream_text": "我梦见森林"}).json()
    monkeypatch.setattr(TextModerator, "check", lambda *_: ModerationDecision("medium", None))
    response = client.put(f"/api/v1/dreams/{dream['id']}/symbols", json={"symbols": dream["symbols"]})
    assert response.status_code == 422
    assert client.get(f"/api/v1/dreams/{dream['id']}").json()["revision"] == dream["revision"]


def test_configuration_is_read_only(tmp_path, monkeypatch):
    monkeypatch.setattr(TextModerator, "check", lambda *_: pytest.fail("unexpected provider call"))
    client = TestClient(create_app(config(DREAMCARD_DATABASE_PATH=tmp_path / "test.db")))
    response = client.get("/api/v1/moderation/configuration")
    assert response.status_code == 200
    assert response.json()["credentials_configured"] is True
    assert response.json()["live_connection_verified"] is False
    assert "fixture-secret" not in response.text
