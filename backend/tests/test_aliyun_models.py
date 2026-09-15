import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.main import create_app
from app.schemas.dream import DreamSessionResponse, DreamSymbols
from app.services.aliyun import AliyunModels, ModelServiceError
from app.services.interpretation import (
    InterpretationDraft,
    SourcePassage,
    compact_card_summary,
    draft_interpretation,
    ensure_reality_calibration,
    image_prompt,
    normalize_chinese_typography,
)


class Answer(BaseModel):
    answer: str


def settings(**kwargs):
    return Settings(_env_file=None, DREAMCARD_MODEL_MODE="aliyun", DASHSCOPE_API_KEY="test-secret", **kwargs)


def models_for(handler):
    return AliyunModels(settings(), httpx.MockTransport(handler))


def chat_response(content, finish="stop"):
    return httpx.Response(200, json={"choices": [{"finish_reason": finish,
                         "message": {"content": json.dumps(content, ensure_ascii=False)}}]})


def test_chat_wire_contract():
    def handler(request):
        assert request.url.path == "/compatible-mode/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer test-secret"
        body = json.loads(request.content)
        assert body["enable_thinking"] is False
        assert body["enable_search"] is False
        assert body["response_format"] == {"type": "json_object"}
        assert "JSON" in body["messages"][0]["content"]
        return chat_response({"answer": "ok"})
    assert models_for(handler).chat_json("qwen3.7-plus", "system", "input", Answer).answer == "ok"


def test_embedding_wire_contract_and_ordering():
    def handler(request):
        assert request.url.path == "/compatible-mode/v1/embeddings"
        body = json.loads(request.content)
        assert body["model"] == "text-embedding-v4"
        assert body["input"] == ["forest", "deer"]
        assert body["dimensions"] == 512
        return httpx.Response(200, json={
            "model": "text-embedding-v4",
            "data": [
                {"index": 1, "embedding": [0.2] * 512},
                {"index": 0, "embedding": [0.1] * 512},
            ],
            "usage": {"total_tokens": 2},
        })
    result = models_for(handler).embed_texts(["forest", "deer"])
    assert result.model == "text-embedding-v4"
    assert result.total_tokens == 2
    assert result.vectors[0][0] == pytest.approx(0.1)


@pytest.mark.parametrize("texts,code", [
    ([], "embedding_batch_invalid"),
    (["x"] * 11, "embedding_batch_invalid"),
    ([" "], "embedding_text_invalid"),
])
def test_embedding_input_validation(texts, code):
    with pytest.raises(ModelServiceError, match=code):
        models_for(lambda request: pytest.fail("must not call network")).embed_texts(texts)


def test_embedding_rejects_wrong_dimensions():
    response = {"model": "text-embedding-v4", "data": [{"index": 0, "embedding": [0.1]}]}
    with pytest.raises(ModelServiceError, match="model_invalid_response"):
        models_for(lambda request: httpx.Response(200, json=response)).embed_texts(["forest"])


def test_rerank_wire_contract():
    def handler(request):
        assert request.url.path == "/compatible-api/v1/reranks"
        body = json.loads(request.content)
        assert body == {
            "model": "qwen3-rerank", "query": "deer", "documents": ["deer", "airplane"],
            "top_n": 2, "instruct": "Retrieve semantically similar dream-symbol passages.",
        }
        return httpx.Response(200, json={
            "model": "qwen3-rerank",
            "results": [
                {"index": 0, "relevance_score": 0.91},
                {"index": 1, "relevance_score": 0.12},
            ],
            "usage": {"total_tokens": 8},
        })
    result = models_for(handler).rerank_texts("deer", ["deer", "airplane"], 2)
    assert result.model == "qwen3-rerank"
    assert result.total_tokens == 8
    assert [item.index for item in result.results] == [0, 1]


@pytest.mark.parametrize("query,documents,top_n,code", [
    (" ", ["one"], 1, "rerank_query_invalid"),
    ("query", [], 1, "rerank_documents_invalid"),
    ("query", [" "], 1, "rerank_documents_invalid"),
    ("query", ["one"], 2, "rerank_top_n_invalid"),
])
def test_rerank_input_validation(query, documents, top_n, code):
    with pytest.raises(ModelServiceError, match=code):
        models_for(lambda request: pytest.fail("must not call network")).rerank_texts(
            query, documents, top_n
        )


def test_rerank_rejects_invalid_provider_order_and_index():
    for results in [
        [{"index": 0, "relevance_score": 0.1}, {"index": 1, "relevance_score": 0.9}],
        [{"index": 0, "relevance_score": 0.9}, {"index": 0, "relevance_score": 0.8}],
        [{"index": 2, "relevance_score": 0.9}, {"index": 1, "relevance_score": 0.8}],
    ]:
        with pytest.raises(ModelServiceError, match="model_invalid_response"):
            models_for(lambda request, body=results: httpx.Response(200, json={
                "model": "qwen3-rerank", "results": body,
            })).rerank_texts("query", ["one", "two"], 2)


@pytest.mark.parametrize("status,code", [(401, "model_auth_failed"), (403, "model_auth_failed"),
    (429, "model_rate_limited"), (503, "model_unavailable"), (400, "model_request_rejected"),
    (302, "model_request_rejected")])
def test_safe_errors_and_no_automatic_retry(status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={"message": "test-secret PRIVATE DREAM"})
    with pytest.raises(ModelServiceError) as error:
        models_for(handler).chat_json("model", "s", "u", Answer)
    assert error.value.code == code
    assert "test-secret" not in str(error.value)
    assert "PRIVATE" not in str(error.value)
    assert len(calls) == 1


@pytest.mark.parametrize("body", [[], {}, {"choices": []}, {"choices": [None]}, {"code": "Rejected"}])
def test_invalid_provider_bodies(body):
    with pytest.raises(ModelServiceError):
        models_for(lambda request: httpx.Response(200, json=body)).chat_json("m", "s", "u", Answer)


def test_schema_validation_and_truncation():
    for body, finish in [({"wrong": "field"}, "stop"), ({"answer": "ok"}, "length")]:
        with pytest.raises(ModelServiceError, match="model_invalid_response"):
            models_for(lambda req: chat_response(body, finish)).chat_json("m", "s", "u", Answer)


def test_timeout():
    def handler(request):
        raise httpx.ReadTimeout("private response", request=request)
    with pytest.raises(ModelServiceError, match="model_timeout"):
        models_for(handler).submit_image("测试")


def test_configuration_never_calls_network_without_opt_in():
    def forbidden(request):
        pytest.fail("unexpected network call")
    for config, code in [
        (Settings(_env_file=None, DREAMCARD_MODEL_MODE="mock", DASHSCOPE_API_KEY="x"), "aliyun_mode_required"),
        (Settings(_env_file=None, DREAMCARD_MODEL_MODE="aliyun", DASHSCOPE_API_KEY=" "), "api_key_missing"),
    ]:
        with pytest.raises(ModelServiceError, match=code):
            AliyunModels(config, httpx.MockTransport(forbidden)).submit_image("测试")
    assert "test-secret" not in repr(settings())
    with pytest.raises(ValidationError):
        settings(DASHSCOPE_API_HOST="https://example.com")


def test_image_submit_and_poll():
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == "POST":
            assert request.url.path == "/api/v1/services/aigc/image-generation/generation"
            assert request.headers["X-DashScope-Async"] == "enable"
            payload = json.loads(request.content)
            assert payload["parameters"]["n"] == 1
            assert payload["parameters"]["prompt_extend"] is False
            assert payload["parameters"]["watermark"] is False
            assert payload["parameters"]["size"] == "960*1280"
            assert "四宫格" in payload["parameters"]["negative_prompt"]
            assert "重复的主体" in payload["parameters"]["negative_prompt"]
            assert "四宫格" not in payload["input"]["messages"][0]["content"][0]["text"]
            assert "thinking_mode" not in payload["parameters"]
            assert "enable_sequential" not in payload["parameters"]
            assert payload["model"] == "qwen-image-3.0-pro"
            return httpx.Response(200, json={"output": {"task_id": "task-1", "task_status": "PENDING"}})
        assert request.url.path == "/api/v1/tasks/task-1"
        return httpx.Response(200, json={"output": {"task_id": "task-1", "task_status": "SUCCEEDED",
            "choices": [{"message": {"content": [{"image": "https://example.com/result.png"}]}}]}})
    models = models_for(handler)
    pending = models.submit_image("月光下森林中的鹿")
    assert pending.status == "PENDING"
    result = models.get_image_task(pending.task_id)
    assert result.status == "SUCCEEDED" and len(result.image_urls) == 1
    assert result.review_status == "pending"
    assert len(calls) == 2


@pytest.mark.parametrize("status", ["PENDING", "RUNNING", "FAILED", "CANCELED", "UNKNOWN"])
def test_image_states(status):
    models = models_for(lambda req: httpx.Response(200, json={"output": {"task_id": "task-1", "task_status": status}}))
    assert models.get_image_task("task-1").status == status


def test_invalid_image_task():
    models = models_for(lambda req: httpx.Response(200, json={"output": {"task_id": "task-1", "task_status": "SUCCEEDED"}}))
    with pytest.raises(ModelServiceError, match="model_invalid_response"):
        models.get_image_task("task-1")
    with pytest.raises(ModelServiceError, match="image_task_id_invalid"):
        models.get_image_task("../secret")


def session(status="ready_to_generate"):
    return DreamSessionResponse(id="test", dream_text="不该再次传给解读模型的原文",
        status=status, symbols=DreamSymbols(
            scenes=["森林"],
            characters=["鹿"],
            reality_context=["最近工作上要在月底向领导汇报项目，也担心全部返工"],
        ),
        revision=2, created_at="test", updated_at="test", model_mode="aliyun")


def draft_payload(source_id="fixture", quote="这是测试片段"):
    return {"title": "测试梦境", "readings": [{"source_id": source_id, "quote": quote, "reading": "仅用于接口测试"}],
            "reflection_question": "梦中有什么感受", "image_scene": "森林中的鹿",
            "image_style": "柔和插画", "style_reason": "表现确认梦象中的森林与鹿"}


def test_interpretation_citation_contract():
    passage = SourcePassage(id="fixture", book="非真实书籍的测试夹具", location="test:1", text="这是测试片段")
    def handler(request):
        system = json.loads(request.content)["messages"][0]["content"]
        assert "140 至 180 个中文字完整解读" in system
        user = json.loads(json.loads(request.content)["messages"][1]["content"])
        assert "dream_text" not in user
        assert user["confirmed_symbols"]["characters"] == ["鹿"]
        assert "reality_context" not in user["confirmed_symbols"]
        assert user["confirmed_reality_context"] == ["最近工作上要在月底向领导汇报项目，也担心全部返工"]
        return chat_response(draft_payload())
    draft = draft_interpretation(session(), [passage], models_for(handler))
    assert "森林" in image_prompt(session(), draft)
    assert "最近的生活" in draft.reflection_question
    assert "梦幻动画电影背景美术" in image_prompt(session(), draft)
    assert "三分现实可信度与七分梦幻艺术化" in image_prompt(session(), draft)
    # Composition is positive prose; exclusions now live in negative_prompt.
    assert "自然边缘" in image_prompt(session(), draft)
    assert "同一机位、同一时刻、同一连续空间" in image_prompt(session(), draft)
    assert "完整铺满3:4竖幅画布" in image_prompt(session(), draft)
    assert "每个角色只出现一次" in image_prompt(session(), draft)
    assert "水彩纸纹" not in image_prompt(session(), draft)
    assert "左右分栏" not in image_prompt(session(), draft)
    assert "dream_text" not in image_prompt(session(), draft)
    for bad in [draft_payload("invented"), draft_payload(quote="伪造引文")]:
        with pytest.raises(ModelServiceError, match="source_citation_invalid"):
            draft_interpretation(session(), [passage], models_for(lambda req: chat_response(bad)))


def test_image_prompt_does_not_inject_unconfirmed_example_subjects():
    clean_session = DreamSessionResponse(
        id="clean-subjects",
        dream_text="只用于测试的走廊梦",
        status="ready_to_generate",
        symbols=DreamSymbols(
            scenes=["走廊"],
            characters=["我", "陌生人"],
            actions=["奔跑", "追赶"],
        ),
        revision=2,
        created_at="test",
        updated_at="test",
        model_mode="aliyun",
    )
    draft = InterpretationDraft.model_validate({
        "title": "无尽走廊",
        "readings": [{
            "source_id": "fixture",
            "quote": "这是测试片段",
            "reading": "仅用于提示词回归测试",
        }],
        "reflection_question": "最近的生活里，你是在等待时机，还是准备推进一件事？",
        "image_scene": "一条延伸的走廊中，一个人奔跑，远处有模糊的陌生人追赶",
        "image_style": "低饱和冷灰蓝色调，柔和漫射光，空气感明显",
        "style_reason": "表现未知与追逐的紧张感",
    })

    prompt = image_prompt(clean_session, draft)

    for unconfirmed_subject in ("森林", "月亮", "鹿"):
        assert unconfirmed_subject not in prompt


def test_reality_question_requires_recent_life_context_and_choices():
    valid = "如果最近现实生活里有某个机会在吸引你，你会靠近观察，还是保持距离等待？"
    assert ensure_reality_calibration(valid) == valid
    longer_valid = "这段时间现实生活里，如果你正面对一件边界不断被打扰的事情，你更想先保护已有安排，还是重新划清能够接受的范围？"
    assert ensure_reality_calibration(longer_valid) == longer_valid
    assert "最近的生活" in ensure_reality_calibration("最近梦里最强烈的感受是什么？")
    assert "最近的生活" in ensure_reality_calibration("现实生活里最近感觉怎么样？")


def test_card_summary_keeps_more_interpretive_context_without_exceeding_card_limit():
    sentence = "窗外不断涌入的猫让熟悉空间失去边界，也让保护原有宠物的动作变得突出。"
    summary = compact_card_summary(sentence * 5)
    assert 130 <= len(summary) <= 180
    assert summary.endswith("。")


def test_generated_chinese_typography_removes_model_spacing():
    assert normalize_chinese_typography("那种 ‘透明’ 与 ‘易碎’ 并存的感受 。") == "那种‘透明’与‘易碎’并存的感受。"


def test_missing_knowledge_and_unconfirmed_session_do_not_call_models():
    def forbidden(request):
        pytest.fail("must not use model memory as a knowledge base")
    models = models_for(forbidden)
    with pytest.raises(ModelServiceError, match="knowledge_sources_missing"):
        draft_interpretation(session(), [], models)
    with pytest.raises(ModelServiceError, match="symbols_not_confirmed"):
        draft_interpretation(session("safety_interrupted"), [], models)


@pytest.mark.parametrize("index_available", [False, True])
def test_configuration_endpoint_is_not_live_verification(tmp_path, index_available):
    # Configuration checks must not depend on a developer's untracked index.
    from app.services.knowledge_index import KnowledgeIndex

    index_path = tmp_path / "knowledge.sqlite3"
    configured = settings(DREAMCARD_KNOWLEDGE_INDEX_PATH=index_path)
    if index_available:
        with KnowledgeIndex(index_path, configured.embedding_model, configured.embedding_dimensions):
            pass
    client = TestClient(create_app(configured, database_path=tmp_path / "test.db"))
    result = client.get("/api/v1/models/configuration")
    assert result.status_code == 200
    assert result.json()["api_key_configured"] is True
    assert result.json()["live_connection_verified"] is False
    assert result.json()["generation_endpoint_available"] is index_available
    assert "test-secret" not in result.text
