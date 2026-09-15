import json
import sqlite3
import pytest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.storage.repository import DreamRepository
from app.services.interpretation import InterpretationDraft, PersonalizedInterpretationDraft
from app.services.original_knowledge import LocalOriginalKnowledgeRetriever, OriginalKnowledgeCard
from app.services.retrieval import (
    RetrievalExpansion,
    RetrievalResult,
    RetrievedPassage,
)


SOURCE_TEXT = "A deer crossed the forest quietly."


def test_interrupted_generation_recovers_after_restart_only_on_explicit_retry(tmp_path):
    models, retrieval = FakeGenerationModels(), FakeRetrieval()
    client = make_client(tmp_path, models, retrieval)
    sid = ready_session(client)
    revision = client.get(f'/api/v1/dreams/{sid}').json()['revision']
    repo = DreamRepository(tmp_path / 'test.db')
    assert repo.begin_generation(sid, revision)
    url = f'/api/v1/dreams/{sid}/interpretation'
    assert client.post(url + '?retry=true').status_code == 409
    assert models.calls == 0
    with sqlite3.connect(tmp_path / 'test.db') as db:
        db.execute("UPDATE interpretation_generations SET updated_at = '2000-01-01T00:00:00+00:00'")
    client = make_client(tmp_path, models, retrieval)
    for response in (client.get(url), client.post(url)):
        assert response.status_code == 409
        assert response.json()['error']['code'] == 'generation_interrupted'
    assert models.calls == 0
    assert client.post(url + '?retry=true').status_code == 200
    assert client.post(url + '?retry=true').status_code == 200
    assert models.calls == 1


def test_late_generation_cannot_overwrite_replacement(tmp_path):
    repo = DreamRepository(tmp_path / 'fencing.db')
    assert repo.begin_generation('fixture', 1)
    old = repo.get_generation('fixture', 1)['updated_at']
    repo.expire_generation('fixture', 1, timeout_seconds=-1)
    assert repo.retry_generation('fixture', 1)
    new = repo.get_generation('fixture', 1)['updated_at']
    assert new != old
    assert not repo.retry_generation('fixture', 1)
    with pytest.raises(RuntimeError):
        repo.complete_generation('fixture', 1, '{}', started_at=old)
    repo.fail_generation('fixture', 1, 'late_error', started_at=old)
    assert repo.get_generation('fixture', 1)['status'] == 'processing'
    repo.complete_generation('fixture', 1, '{"fresh":true}', started_at=new)
    repo.expire_generation('fixture', 1, timeout_seconds=-1)
    assert repo.get_generation('fixture', 1)['result_json'] == '{"fresh":true}'


class FakeRetrieval:
    def __init__(self):
        self.calls = 0

    def retrieve(self, symbols, clarification_answer):
        self.calls += 1
        assert symbols.characters == ["鹿"]
        return RetrievalResult(
            expansion=RetrievalExpansion(
                english_queries=["deer in forest"], english_keywords=["deer", "forest"]
            ),
            passages=[RetrievedPassage(
                source_id="miller:deer", book="Fixture Book", author="Fixture Author",
                translator=None, chapter="Deer", original_text=SOURCE_TEXT,
                source_url="https://example.com", source_line_start=10, source_line_end=11,
                source_file_sha256="a" * 64, rights_status="candidate", verified=False,
                hybrid_score=0.05, rerank_score=0.91,
            )],
            embedding_tokens=4, rerank_tokens=12,
        )


class FakeGenerationModels:
    def __init__(self, valid_quote=True):
        self.calls = 0
        self.valid_quote = valid_quote
        self.settings = SimpleNamespace(qwen_interpret_model="fixture-model")

    def chat_json(self, _model, _system, _user, schema):
        self.calls += 1
        assert schema is InterpretationDraft
        return schema(
            title="森林中的鹿",
            readings=[{
                "source_id": "miller:deer",
                "quote": "A deer crossed the forest" if self.valid_quote else "invented quote",
                "reading": "这个条目与已确认的鹿和森林场景相关。",
            }],
            reflection_question="你在看到鹿时最先注意到什么？",
            image_scene="月光下森林中的鹿",
            image_style="安静的柔和插画",
            style_reason="对应已确认的森林、鹿和平静情绪。",
        )


class FakeFallbackModels:
    def __init__(self):
        self.calls = 0
        self.settings = SimpleNamespace(qwen_interpret_model="fixture-model")
        self.last_user_payload = None
        self.last_system = None

    def chat_json(self, _model, _system, _user, schema):
        self.calls += 1
        assert schema is PersonalizedInterpretationDraft
        self.last_system = _system
        self.last_user_payload = json.loads(_user)
        return schema(
            title="月球商店的片段",
            opening="这场梦有着不太寻常的轮廓。接下来，我们会循着你留下的片段，为它整理一份专属解读。",
            dream_summary="你确认了月球商店、蓝色纽扣与安静的感受。",
            reflections=[
                "梦里反复数着蓝色纽扣，也许表达了你正在留意现实中某些细小却反复出现的事，例如需要整理的任务或尚未说清的需要。",
                "安静的商店与陌生环境并存，可能像是一种隐喻：你在新鲜而不确定的处境里仍在尝试建立秩序，可以对照近期的新计划或新环境。",
            ],
            card_summary="在陌生的月球商店里数着蓝色纽扣，可能像是在不确定环境中借细小线索建立秩序。如果最近正面对新计划，这份安静也许是耐心观察的空间。",
            reflection_question="醒来后最先留下的是哪一个画面？",
            gentle_action="写下那个最先浮现的画面，不急着解释它。",
            image_scene="月球商店里散落着蓝色纽扣",
            image_style="安静的浅色插画",
            style_reason="对应已确认的场景、物件与安静感受。",
        )


def unrelated_original_cards() -> LocalOriginalKnowledgeRetriever:
    return LocalOriginalKnowledgeRetriever([
        OriginalKnowledgeCard(
            card_id="DREAM-001", title="森林", aliases=(), retrieval_terms=("树林",),
            category="场景", scope_note="scope", original_interpretation="text",
            reflection_prompts=(), gentle_actions=(), safety_note="safe",
            rights_status="original_pending_review", status="draft", source_file="test.md",
        )
    ])


def matching_original_cards() -> LocalOriginalKnowledgeRetriever:
    return LocalOriginalKnowledgeRetriever([
        OriginalKnowledgeCard(
            card_id="DREAM-029", title="蛇", aliases=("大蛇",), retrieval_terms=("蛇咬",),
            category="动物", scope_note="scope", original_interpretation="text",
            reflection_prompts=(), gentle_actions=(), safety_note="safe",
            rights_status="original_pending_review", status="draft", source_file="test.md",
        )
    ])


def make_client(tmp_path: Path, models, retrieval) -> TestClient:
    settings = Settings(
        _env_file=None, DREAMCARD_ENV="test", DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="disabled",
    )
    return TestClient(create_app(
        settings=settings, models=models, retrieval_service=retrieval
    ))


def ready_session(client: TestClient) -> str:
    created = client.post("/api/v1/dreams/extract", json={
        "dream_text": "我在森林里看见一只鹿，感到平静。"
    }).json()
    symbols = created["symbols"]
    symbols["scenes"] = ["森林"]
    symbols["characters"] = ["鹿"]
    symbols["emotions"] = ["平静"]
    updated = client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": symbols, "clarification_answer": "平静", "character_appearance": "unspecified"
    })
    assert updated.status_code == 200
    assert updated.json()["status"] == "ready_to_generate"
    return created["id"]


def test_generation_is_cited_persisted_and_idempotent(tmp_path):
    models = FakeGenerationModels()
    retrieval = FakeRetrieval()
    client = make_client(tmp_path, models, retrieval)
    session_id = ready_session(client)

    first = client.post(f"/api/v1/dreams/{session_id}/interpretation")
    assert first.status_code == 200
    payload = first.json()
    assert payload["status"] == "completed"
    assert payload["review_status"] == "not_enabled"
    assert payload["production_eligible"] is False
    assert payload["sources"][0]["source_id"] == "miller:deer"
    assert payload["sources"][0]["verified"] is False

    second = client.post(f"/api/v1/dreams/{session_id}/interpretation")
    restored = client.get(f"/api/v1/dreams/{session_id}/interpretation")
    assert second.status_code == restored.status_code == 200
    assert second.json() == restored.json() == payload
    assert models.calls == 1 and retrieval.calls == 1


def test_invalid_citation_is_terminal_and_not_retried(tmp_path):
    models = FakeGenerationModels(valid_quote=False)
    retrieval = FakeRetrieval()
    client = make_client(tmp_path, models, retrieval)
    session_id = ready_session(client)

    first = client.post(f"/api/v1/dreams/{session_id}/interpretation")
    second = client.post(f"/api/v1/dreams/{session_id}/interpretation")
    status = client.get(f"/api/v1/dreams/{session_id}/interpretation")
    assert first.status_code == second.status_code == status.status_code == 503
    assert first.json()["error"]["code"] == "generation_failed"
    assert models.calls == 1 and retrieval.calls == 1

    models.valid_quote = True
    retried = client.post(f"/api/v1/dreams/{session_id}/interpretation?retry=true")
    assert retried.status_code == 200
    assert models.calls == 2 and retrieval.calls == 2


def test_unconfirmed_session_never_calls_generation(tmp_path):
    models = FakeGenerationModels()
    retrieval = FakeRetrieval()
    client = make_client(tmp_path, models, retrieval)
    session_id = client.post("/api/v1/dreams/extract", json={
        "dream_text": "我在森林里看见一只鹿"
    }).json()["id"]
    response = client.post(f"/api/v1/dreams/{session_id}/interpretation")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "symbols_not_confirmed"
    assert models.calls == 0 and retrieval.calls == 0


def test_no_card_match_generates_complete_personalized_reading(tmp_path):
    models = FakeFallbackModels()
    retrieval = FakeRetrieval()
    settings = Settings(
        _env_file=None, DREAMCARD_ENV="test", DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
    )
    client = TestClient(create_app(
        settings=settings,
        models=models,
        retrieval_service=retrieval,
        original_knowledge_retriever=unrelated_original_cards(),
    ))
    created = client.post("/api/v1/dreams/extract", json={
        "dream_text": (
            "我在月球商店里数蓝色纽扣，四周很安静。"
            "最近工作上要在月底向领导汇报项目，也担心全部返工。"
        )
    }).json()
    updated = client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": created["symbols"], "clarification_answer": "平静或放松", "character_appearance": "unspecified"
    })
    assert updated.status_code == 200

    response = client.post(f"/api/v1/dreams/{created['id']}/interpretation")
    assert response.status_code == 200
    payload = response.json()
    assert payload["generation_mode"] == "personalized"
    assert payload["sources"] == []
    assert payload["interpretation"]["opening"] == "这场梦有着不太寻常的轮廓。接下来，我们会循着你留下的片段，为它整理一份专属解读。"
    assert len(payload["interpretation"]["reflections"]) == 2
    assert "月球商店" in payload["interpretation"]["card_summary"]
    assert "最近的生活" in payload["interpretation"]["reflection_question"]
    assert "近期清醒时的真实生活" in models.last_system
    assert "不得只追问梦中画面" in models.last_system
    assert "也不要推断现实中存在某种压力" not in models.last_system
    assert "不得增加、删除或改写" in models.last_system
    assert "不得要求清晰五官" in models.last_system
    assert "每次都必须与用户已确认的一个具体梦境细节绑定" in models.last_system
    assert "现实处境要写出可识别的事件或行动" in models.last_system
    assert "不得用‘觉察与行动的边界’" in models.last_system
    assert "必须降低确定语气" in models.last_system
    assert models.last_user_payload["confirmed_reality_context"] == [
        "最近工作上要在月底向领导汇报项目，也担心全部返工"
    ]
    assert "reality_context" not in models.last_user_payload["confirmed_symbols"]
    assert "不得将其泛化" in models.last_system
    assert models.calls == 1 and retrieval.calls == 0


def test_draft_card_match_still_uses_personalized_reading(tmp_path):
    models = FakeFallbackModels()
    retrieval = FakeRetrieval()
    settings = Settings(
        _env_file=None, DREAMCARD_ENV="test", DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
    )
    client = TestClient(create_app(
        settings=settings,
        models=models,
        retrieval_service=retrieval,
        original_knowledge_retriever=matching_original_cards(),
    ))
    created = client.post("/api/v1/dreams/extract", json={
        "dream_text": "一条蛇咬了我"
    }).json()
    symbols = created["symbols"]
    symbols["characters"] = ["蛇"]
    updated = client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": symbols, "clarification_answer": "紧张或害怕", "character_appearance": "unspecified"
    })
    assert updated.status_code == 200

    response = client.post(f"/api/v1/dreams/{created['id']}/interpretation")
    assert response.status_code == 200
    assert response.json()["generation_mode"] == "personalized"
    assert models.calls == 1 and retrieval.calls == 0
    assert models.last_user_payload["selected_card_context"] == [{
        "role": "primary",
        "title": "蛇",
        "category": "动物",
        "matched_terms": ["蛇"],
        "scope_note": "scope",
        "original_interpretation": "text",
        "reflection_prompts": [],
        "gentle_actions": [],
        "safety_note": "safe",
    }]
