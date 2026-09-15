from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.schemas.dream import DreamSymbols, ExtractionResult
from app.services.extractor import DreamExtractor


def make_client(tmp_path: Path) -> TestClient:
    settings = Settings(
        DREAMCARD_ENV="test",
        DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
    )
    return TestClient(create_app(settings=settings))


def test_health(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "model_mode": "mock"}


def test_extract_update_restore_and_delete(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/dreams/extract",
        json={"dream_text": "我在森林里看见一只鹿，然后一直奔跑，但记不清自己的感受。"},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "reviewing_symbols"
    assert "森林" in created["symbols"]["scenes"]
    assert "鹿" in created["symbols"]["characters"]
    assert created["clarification"] is not None
    assert created["model_mode"] == "mock"

    session_id = created["id"]
    symbols = created["symbols"]
    symbols["emotions"] = ["紧张"]
    updated_response = client.put(
        f"/api/v1/dreams/{session_id}/symbols",
            json={"symbols": symbols, "clarification_answer": "紧张或害怕", "character_appearance": "unspecified"},
    )
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["status"] == "ready_to_generate"
    assert updated["revision"] == 2

    restored = client.get(f"/api/v1/dreams/{session_id}")
    assert restored.status_code == 200
    assert restored.json()["symbols"]["emotions"] == ["紧张"]

    deleted = client.delete(f"/api/v1/dreams/{session_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
    assert client.get(f"/api/v1/dreams/{session_id}").status_code == 404


def test_extract_keeps_explicit_luggage_as_an_editable_object(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/dreams/extract",
        json={"dream_text": "我在搬家，房间里堆满了行李。"},
    )
    assert response.status_code == 200
    assert "行李" in response.json()["symbols"]["objects"]


def test_extract_keeps_explicit_deceased_person_state(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/dreams/extract",
        json={"dream_text": "我梦见已经去世的外婆坐在窗边织毛衣。"},
    )

    assert response.status_code == 200
    symbols = response.json()["symbols"]
    assert "已经去世的外婆" in symbols["characters"]
    assert "外婆已经去世" in symbols["relationships"]


def test_extract_separates_recent_reality_context(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/dreams/extract",
        json={
            "dream_text": (
                "我梦见自己回到高中参加考试，紧张得写不出字。"
                "最近工作上接了重要项目，月底要向领导汇报，也担心全部返工。"
            )
        },
    )

    assert response.status_code == 200
    reality_context = response.json()["symbols"]["reality_context"]
    assert reality_context == ["最近工作上接了重要项目，月底要向领导汇报，也担心全部返工"]


def test_missing_emotion_always_uses_single_clarification_for_felt_tone() -> None:
    result = DreamExtractor._ensure_emotion_clarification(ExtractionResult(
        symbols=DreamSymbols(scenes=["透明森林"], uncertain_fields=[]),
        clarification=None,
    ))

    assert result.clarification is not None
    assert result.clarification.question == "你在这个梦里最接近哪种感受？"
    assert "好奇或期待" in result.clarification.options
    assert "记不清" in result.clarification.options
    assert "梦中的主要情绪" in result.symbols.uncertain_fields


def test_explicit_emotion_does_not_add_clarification() -> None:
    result = DreamExtractor._ensure_emotion_clarification(ExtractionResult(
        symbols=DreamSymbols(emotions=["平静"]),
        clarification=None,
    ))

    assert result.clarification is None


def test_empty_and_too_long_inputs_use_safe_errors(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    empty = client.post("/api/v1/dreams/extract", json={"dream_text": "   "})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "validation_error"

    too_long = client.post(
        "/api/v1/dreams/extract", json={"dream_text": "梦" * 301}
    )
    assert too_long.status_code == 422
    assert too_long.json()["error"]["code"] == "dream_too_long"


def test_crisis_input_interrupts_normal_flow(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.post(
        "/api/v1/dreams/extract",
        json={"dream_text": "我梦见自己不想活，醒来后也很害怕。"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "safety_interrupted"
    assert payload["safety_message"]


def test_missing_session_returns_unified_error(tmp_path: Path) -> None:
    client = make_client(tmp_path)
    response = client.get("/api/v1/dreams/missing")
    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "没有找到这次梦境记录"}
    }
