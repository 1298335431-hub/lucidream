import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.storage.repository import DreamRepository


def write_cards(path: Path) -> None:
    records = [{
        "card_id": "DREAM-001",
        "title": "被追赶",
        "aliases": ["追逐"],
        "retrieval_terms": ["追赶", "被人追"],
        "category": "动作",
        "scope_note": "scope",
        "original_interpretation": "text",
        "reflection_prompts": [],
        "gentle_actions": [],
        "safety_note": "safe",
        "rights_status": "original_pending_review",
        "status": "draft",
        "source_file": "DREAM-001.md",
    }, {
        "card_id": "DREAM-029",
        "title": "蛇",
        "aliases": ["大蛇", "小蛇"],
        "retrieval_terms": ["蛇", "很多蛇"],
        "category": "动物",
        "scope_note": "scope",
        "original_interpretation": "text",
        "reflection_prompts": [],
        "gentle_actions": [],
        "safety_note": "safe",
        "rights_status": "original_pending_review",
        "status": "draft",
        "source_file": "DREAM-029.md",
    }]
    path.write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
    )


def make_client(tmp_path: Path, *, mode: str = "local") -> tuple[TestClient, Path]:
    cards_path = tmp_path / "cards.jsonl"
    write_cards(cards_path)
    database_path = tmp_path / "test.db"
    settings = Settings(
        _env_file=None,
        DREAMCARD_ENV="test",
        DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=database_path,
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE=mode,
        DREAMCARD_ORIGINAL_KNOWLEDGE_CARDS_PATH=cards_path,
    )
    return TestClient(create_app(settings=settings)), database_path


def confirm_symbols(client: TestClient, dream_text: str, actions: list[str]) -> dict:
    created = client.post(
        "/api/v1/dreams/extract", json={"dream_text": dream_text}
    ).json()
    symbols = created["symbols"]
    symbols["actions"] = actions
    response = client.put(
        f"/api/v1/dreams/{created['id']}/symbols",
            json={"symbols": symbols, "clarification_answer": "紧张或害怕", "character_appearance": "unspecified"},
    )
    assert response.status_code == 200
    return response.json()


def test_shadow_records_hit_without_changing_response(tmp_path: Path) -> None:
    client, database_path = make_client(tmp_path)
    updated = confirm_symbols(client, "我梦见被人追赶", ["追赶"])

    assert "shadow" not in updated
    record = DreamRepository(database_path).get_original_knowledge_shadow(
        updated["id"], updated["revision"]
    )
    assert record is not None
    assert record["fallback"] is False
    assert record["hits"][0]["card_id"] == "DREAM-001"
    assert record["hits"][0]["role"] == "primary"
    assert record["hits"][0]["matched_terms"] == ["追赶"]
    assert DreamRepository(database_path).summarize_original_knowledge_shadow() == {
        "total_runs": 1,
        "matched_runs": 1,
        "fallback_runs": 0,
        "match_rate": 1.0,
        "card_hits": {"DREAM-001": 1},
        "includes_user_text": False,
        "model_calls": 0,
    }

    configuration = client.get("/api/v1/knowledge/shadow/configuration").json()
    assert configuration == {
        "mode": "local",
        "status": "ready",
        "card_count": 2,
        "changes_user_output": False,
        "uses_cloud_model": False,
        "production_eligible": False,
    }


def test_shadow_records_fallback_and_deletes_with_session(tmp_path: Path) -> None:
    client, database_path = make_client(tmp_path)
    updated = confirm_symbols(client, "我在月球商店散步", ["散步"])
    repository = DreamRepository(database_path)
    record = repository.get_original_knowledge_shadow(
        updated["id"], updated["revision"]
    )
    assert record is not None
    assert record["fallback"] is True
    assert record["hits"] == []

    assert client.delete(f"/api/v1/dreams/{updated['id']}").status_code == 200
    assert (
        repository.get_original_knowledge_shadow(updated["id"], updated["revision"])
        is None
    )
    # A deleted session must not erase anonymous evaluation history.
    assert repository.summarize_original_knowledge_shadow() == {
        "total_runs": 1,
        "matched_runs": 0,
        "fallback_runs": 1,
        "match_rate": 0.0,
        "card_hits": {},
        "includes_user_text": False,
        "model_calls": 0,
    }
    with repository._connect() as connection:
        metric_columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(original_knowledge_shadow_metrics)"
            ).fetchall()
        }
    assert metric_columns == {"metric_id", "fallback", "hits_json", "created_at"}


def test_shadow_retrieves_confirmed_single_character_animal(tmp_path: Path) -> None:
    client, database_path = make_client(tmp_path)
    created = client.post("/api/v1/dreams/extract", json={"dream_text": "我看见一条蛇"}).json()
    symbols = created["symbols"]
    symbols["characters"] = ["蛇"]
    response = client.put(
        f"/api/v1/dreams/{created['id']}/symbols",
        json={"symbols": symbols, "clarification_answer": "紧张或害怕", "character_appearance": "unspecified"},
    )
    assert response.status_code == 200

    record = DreamRepository(database_path).get_original_knowledge_shadow(
        created["id"], response.json()["revision"]
    )
    assert record is not None
    assert record["fallback"] is False
    assert record["hits"][0]["card_id"] == "DREAM-029"
    assert record["hits"][0]["matched_terms"] == ["蛇"]


def test_disabled_shadow_writes_nothing(tmp_path: Path) -> None:
    client, database_path = make_client(tmp_path, mode="disabled")
    updated = confirm_symbols(client, "我梦见被人追赶", ["追赶"])
    assert (
        DreamRepository(database_path).get_original_knowledge_shadow(
            updated["id"], updated["revision"]
        )
        is None
    )
    configuration = client.get("/api/v1/knowledge/shadow/configuration").json()
    assert configuration["status"] == "disabled"
    assert configuration["card_count"] == 0


def test_missing_shadow_cards_fail_open(tmp_path: Path) -> None:
    database_path = tmp_path / "test.db"
    settings = Settings(
        _env_file=None,
        DREAMCARD_ENV="test",
        DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=database_path,
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
        DREAMCARD_ORIGINAL_KNOWLEDGE_CARDS_PATH=tmp_path / "missing.jsonl",
    )
    client = TestClient(create_app(settings=settings))
    updated = confirm_symbols(client, "我梦见被人追赶", ["追赶"])
    assert updated["status"] == "ready_to_generate"
    configuration = client.get("/api/v1/knowledge/shadow/configuration").json()
    assert configuration["status"] == "cards_unavailable"
    assert configuration["card_count"] == 0
