from pathlib import Path
from types import SimpleNamespace
import json
import pytest

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app
from app.services.aliyun import ImageTask
from app.services.image_quality import ImageQualityResult
from app.services.interpretation import PersonalizedInterpretationDraft
from app.services.interpretation import image_prompt
from app.schemas.dream import DreamSessionResponse, DreamSymbols
from app.services.original_knowledge import LocalOriginalKnowledgeRetriever, OriginalKnowledgeCard


class ImageModels:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(qwen_interpret_model="fixture-model")
        self.image_submissions = 0
        self.polls = 0
        self.last_prompt = ""

    def chat_json(self, _model, _system, _user, schema):
        assert schema is PersonalizedInterpretationDraft
        return schema(
            title="森林里的鹿",
            opening="这场梦有着不太寻常的轮廓。接下来，我们会循着你留下的片段，为它整理一份专属解读。",
            dream_summary="你确认了森林和鹿。",
            reflections=["也许可以回想鹿停下的位置。", "可能有一个画面值得留下。"],
            reflection_question="你最先记住了什么？",
            gentle_action="写下一句醒来后的感受。",
            image_scene="月光下的森林和鹿",
            image_style="安静的浅色插画",
            style_reason="对应已确认的森林和鹿。",
        )

    def submit_image(self, prompt: str) -> ImageTask:
        self.last_prompt = prompt
        assert "森林" in prompt and "鹿" in prompt
        self.image_submissions += 1
        return ImageTask(task_id="image-task", status="PENDING")

    def get_image_task(self, task_id: str) -> ImageTask:
        assert task_id == "image-task"
        self.polls += 1
        return ImageTask(
            task_id=task_id,
            status="SUCCEEDED",
            image_urls=["https://example.com/result.png"],
        )

    def review_subject(self, image_url, form):
        return True


@pytest.mark.parametrize("form", ["我变成了一只水母", "我变成了一只螃蟹", "我变成了一只猴子"])
def test_self_transformation_replaces_conflicting_visual_draft(form):
    session = DreamSessionResponse(
        id="appearance-test", dream_text="我进入魔法世界，看见另一位旅人",
        status="ready_to_generate", revision=1, model_mode="mock",
        created_at="2026-09-14T00:00:00Z", updated_at="2026-09-14T00:00:00Z",
        symbols=DreamSymbols(scenes=["魔法世界"], characters=["我", "另一位旅人"], actions=["看见旅人"]),
        character_appearance="other", character_form=form,
    )
    draft = ImageModels().chat_json(None, None, None, PersonalizedInterpretationDraft)
    draft.image_scene = "前景中，一个模糊的背影代表做梦者，正面向远方。"
    original = draft.model_dump()
    for quality_retry in (False, True):
        prompt = image_prompt(session, draft, retry_without_text=quality_retry)
        assert draft.image_scene not in prompt
        assert form in prompt
        assert "另一位旅人" in prompt
        assert "完整身体" in prompt and "不得额外生成人类背影" in prompt
        assert "不能与做梦者合并" in prompt
        assert "角色编号" not in prompt and "dreamer" not in prompt
        assert "画面唯一的当前做梦者" in prompt
    assert draft.model_dump() == original


@pytest.mark.parametrize("appearance,form", [("other", "我变成了一只水母"), ("male", ""), ("female", ""), ("unspecified", "")])
def test_future_self_remains_independent_and_actions_keep_their_owner(appearance, form):
    session = DreamSessionResponse(
        id="role-binding-test", status="ready_to_generate", revision=1, model_mode="mock",
        created_at="2026-09-14T00:00:00Z", updated_at="2026-09-14T00:00:00Z",
        dream_text="我梦见自己漂浮在车站。小女孩说：‘我游动了一下。’我想靠近她。我看见小女孩拿着瓶子。我的母亲站在旁边。",
        symbols=DreamSymbols(
            scenes=["车站"], characters=["我", "穿黄色雨衣的小女孩（年老后的我）", "我的母亲"],
            actions=["漂浮", "靠近", "看见", "游动", "拿着", "站立"],
            relationships=["小女孩是年老后的我", "触手变成了钟表指针"],
            reality_context=["现实经历不进入生图"],
        ),
        character_appearance=appearance, character_form=form,
    )
    original = session.model_dump()
    draft = ImageModels().chat_json(None, None, None, PersonalizedInterpretationDraft)
    for retry in (False, True):
        prompt = image_prompt(session, draft, retry_without_text=retry, retry_without_band=retry)
        assert "角色编号" not in prompt and "JSON" not in prompt
        assert "穿黄色雨衣的小女孩（年老后的我）" in prompt and "我的母亲" in prompt
        assert "这一瞬间当前做梦者正在漂浮" in prompt
        assert "漂浮、靠近、看见" not in prompt
        assert "游动" not in prompt
        assert "年老后的一只水母" not in prompt
        assert "现实经历不进入生图" not in prompt
        assert len(prompt) <= 5000
    assert session.model_dump() == original


def test_removed_action_is_not_reintroduced_from_the_original_dream():
    from app.services.interpretation import _dreamer_actions
    session = SimpleNamespace(dream_text="我游动。我看见小女孩游动。", symbols=DreamSymbols(actions=["看见"]))
    assert _dreamer_actions(session) == ["看见"]


def test_maximum_confirmed_symbols_are_compacted_without_losing_role_binding():
    long_items = [f"第{i}项" + "很长的已确认梦境细节" * 8 for i in range(20)]
    session = DreamSessionResponse(
        id="large-prompt", dream_text="我变成水母并漂浮。", status="ready_to_generate",
        revision=1, model_mode="mock", created_at="2026-09-14T00:00:00Z",
        updated_at="2026-09-14T00:00:00Z",
        symbols=DreamSymbols(
            scenes=long_items, characters=["我", *long_items], objects=long_items,
            actions=["漂浮", *long_items], emotions=long_items, relationships=long_items,
        ),
        character_appearance="other", character_form="我变成了一只水母",
    )
    prompt = image_prompt(
        session,
        ImageModels().chat_json(None, None, None, PersonalizedInterpretationDraft),
    )
    assert len(prompt) <= 5000
    assert "我变成了一只水母" in prompt
    assert "画面唯一的当前做梦者" in prompt


class RejectOnceReviewer:
    def __init__(self, band=False, always=False, panels=False) -> None:
        self.reviews = 0
        self.band = band
        self.always = always
        self.panels = panels

    def review_url(self, _image_url: str) -> ImageQualityResult:
        self.reviews += 1
        rejected = self.always or self.reviews == 1
        return ImageQualityResult(
            accepted=not rejected,
            detected_text_count=int(rejected and not self.band and not self.panels),
            contains_band=rejected and self.band,
            contains_panels=rejected and self.panels,
        )


def test_laundry_prompt_is_one_still_without_unrelated_props():
    session = DreamSessionResponse(
        id='laundry-fixture', status='ready_to_generate', revision=1, model_mode='mock',
        created_at='2026-09-15T00:00:00Z', updated_at='2026-09-15T00:00:00Z',
        dream_text='我站在云朵上的洗衣店。我伸出双手接住彩虹。',
        character_appearance='male',
        symbols=DreamSymbols(scenes=['云朵上的洗衣店', '柜台前', '之后来到沙漠'],
            characters=['穿黄色围裙的河马'], objects=['洗衣机', '彩虹', '星星'],
            actions=['站在', '伸出双手接住'],
            relationships=['河马取出彩虹', '河马将彩虹递给梦者']),
    )
    before = session.model_dump()
    prompt = image_prompt(session, ImageModels().chat_json(None, None, None, PersonalizedInterpretationDraft))
    assert '云朵上的洗衣店' in prompt and '这一瞬间当前做梦者正在伸出双手接住' in prompt
    assert '河马将彩虹递给梦者' in prompt and '每个角色只出现一次' in prompt
    assert not any(word in prompt for word in ['沙漠', '信封', '招牌', '书页', '河马取出彩虹', '上下分区', '四宫格'])
    assert len(prompt) < 650
    assert session.model_dump() == before


class RetrySubmissionFailsModels(ImageModels):
    def submit_image(self, prompt: str) -> ImageTask:
        self.image_submissions += 1
        if self.image_submissions > 1:
            from app.services.aliyun import ModelServiceError
            raise ModelServiceError("model_unavailable")
        return ImageTask(task_id="image-task", status="PENDING")


class UnavailableReviewer:
    def review_url(self, _image_url: str) -> ImageQualityResult:
        from app.services.aliyun import ModelServiceError
        raise ModelServiceError("image_review_unavailable")


class SubmissionTimeoutModels(ImageModels):
    def submit_image(self, prompt: str) -> ImageTask:
        from app.services.aliyun import ModelServiceError
        self.image_submissions += 1
        raise ModelServiceError("model_timeout")


def prepared_image_client(tmp_path: Path, models, reviewer=None, authenticated=False):
    settings = Settings(
        _env_file=None, DREAMCARD_ENV="test", DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
        DREAMCARD_AUTH_ENABLED=authenticated,
    )
    cards = LocalOriginalKnowledgeRetriever([
        OriginalKnowledgeCard(
            card_id="DREAM-001", title="鹿", aliases=(), retrieval_terms=("鹿",),
            category="动物", scope_note="scope", original_interpretation="text",
            reflection_prompts=(), gentle_actions=(), safety_note="safe",
            rights_status="original_pending_review", status="draft", source_file="test.md",
        )
    ])
    client = TestClient(create_app(
        settings=settings, models=models, image_reviewer=reviewer,
        original_knowledge_retriever=cards,
    ))
    if authenticated:
        _, code = client.app.state.invite_auth.issue()
        assert client.post("/api/v1/auth/login", json={"invite_code": code}).status_code == 200
    created = client.post("/api/v1/dreams/extract", json={"dream_text": "我在森林里看见一只鹿。"}).json()
    symbols = created["symbols"]
    symbols["scenes"] = ["森林"]
    symbols["characters"] = ["鹿"]
    assert client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": symbols, "character_appearance": "unspecified",
        "clarification_answer": (created["clarification"] or {"options": [None]})["options"][0],
    }).status_code == 200
    assert client.post(f"/api/v1/dreams/{created['id']}/interpretation").status_code == 200
    return client, created["id"]


def test_account_quota_blocks_ninth_before_model_submission(tmp_path):
    models = ImageModels()
    client, session_id = prepared_image_client(tmp_path, models, authenticated=True)
    auth = client.app.state.invite_auth
    account = client.get('/api/v1/auth/me').json()['account_id']
    assert client.get('/api/v1/account/quota').json() == {'total': 8, 'used': 0, 'remaining': 8}
    for i in range(8):
        assert auth.reserve_image(account, f'previous-{i}', 1)
    response = client.post(f'/api/v1/dreams/{session_id}/image')
    assert response.status_code == 403
    assert response.json()['error']['code'] == 'image_quota_exhausted'
    assert response.json()['error']['message'] == '额度不足'
    assert models.image_submissions == 0


def test_eighth_task_recovery_is_free_and_deletion_does_not_refund(tmp_path):
    models = ImageModels()
    models.get_image_task = lambda task_id: ImageTask(task_id=task_id, status='FAILED')
    client, session_id = prepared_image_client(tmp_path, models, authenticated=True)
    auth = client.app.state.invite_auth
    account = client.get('/api/v1/auth/me').json()['account_id']
    for i in range(7):
        assert auth.reserve_image(account, f'previous-{i}', 1)
    assert client.post(f'/api/v1/dreams/{session_id}/image').status_code == 200
    assert client.post(f'/api/v1/dreams/{session_id}/image?retry=true').status_code == 200
    assert models.image_submissions == 2
    assert auth.quota(account)['used'] == 8
    assert client.delete(f'/api/v1/dreams/{session_id}').status_code == 200
    assert auth.quota(account)['remaining'] == 0


def test_quality_review_outage_retains_image_and_does_not_stick_processing(tmp_path: Path):
    models = ImageModels()
    client, session_id = prepared_image_client(tmp_path, models, UnavailableReviewer())
    result = client.post(f"/api/v1/dreams/{session_id}/image")
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert result.json()["failure_reason"] == "image_review_unavailable"
    assert result.json()["image_url"].endswith("/image/file")
    assert models.image_submissions == 1


def test_submission_timeout_is_not_blindly_resubmitted(tmp_path: Path):
    models = SubmissionTimeoutModels()
    client, session_id = prepared_image_client(tmp_path, models)
    result = client.post(f"/api/v1/dreams/{session_id}/image")
    assert result.status_code == 503
    state = client.get(f"/api/v1/dreams/{session_id}/image")
    assert state.json()["status"] == "failed"
    assert state.json()["failure_reason"] == "submission_unknown"
    assert models.image_submissions == 1
    assert state.json()['recovery_action'] == 'contact_support'
    for _ in range(3):
        client.post(f'/api/v1/dreams/{session_id}/image?retry=true&regenerate=true')
    assert models.image_submissions == 1


def test_confirmed_provider_failure_has_only_one_user_retry(tmp_path: Path):
    models = ImageModels()
    models.get_image_task = lambda task_id: ImageTask(task_id=task_id, status='FAILED')
    client, session_id = prepared_image_client(tmp_path, models)
    initial = client.post(f'/api/v1/dreams/{session_id}/image').json()
    assert initial['recovery_action'] == 'retry_generation'
    final = client.post(f'/api/v1/dreams/{session_id}/image?retry=true').json()
    assert final['status'] == 'failed'
    assert final['supplementary_attempts'] == 1
    assert final['recovery_action'] == 'contact_support'
    for _ in range(3):
        client.post(f'/api/v1/dreams/{session_id}/image?retry=true&regenerate=true')
    assert models.image_submissions == 2
    assert client.get(f'/api/v1/dreams/{session_id}/interpretation').status_code == 200


def test_timeout_checks_existing_task_instead_of_submitting_again(tmp_path: Path):
    import sqlite3
    models = ImageModels()
    models.get_image_task = lambda task_id: ImageTask(task_id=task_id, status='RUNNING')
    client, session_id = prepared_image_client(tmp_path, models)
    assert client.post(f'/api/v1/dreams/{session_id}/image').json()['status'] == 'processing'
    with sqlite3.connect(tmp_path / 'test.db') as connection:
        connection.execute("UPDATE image_generations SET updated_at='2000-01-01T00:00:00+00:00' WHERE session_id=?", (session_id,))
    state = client.get(f'/api/v1/dreams/{session_id}/image').json()
    assert state['failure_reason'] == 'generation_timeout'
    assert state['recovery_action'] == 'check_task'
    client.post(f'/api/v1/dreams/{session_id}/image?retry=true')
    assert models.image_submissions == 1
    models.get_image_task = lambda task_id: ImageTask(task_id=task_id, status='SUCCEEDED', image_urls=['https://example.com/recovered.png'])
    assert client.post(f'/api/v1/dreams/{session_id}/image/review').json()['status'] == 'completed'
    assert models.image_submissions == 1


def test_manual_retry_and_quality_retry_share_one_budget(tmp_path: Path):
    models = ImageModels()
    reviewer = RejectOnceReviewer(always=True)
    original_poll = models.get_image_task
    models.get_image_task = lambda task_id: ImageTask(task_id=task_id, status='FAILED')
    client, session_id = prepared_image_client(tmp_path, models, reviewer)
    client.post(f'/api/v1/dreams/{session_id}/image')
    models.get_image_task = original_poll
    result = client.post(f'/api/v1/dreams/{session_id}/image?retry=true').json()
    assert result['status'] == 'completed'
    assert result['failure_reason'] == 'contains_text'
    assert models.image_submissions == 2


@pytest.mark.parametrize("appearance,expected", [("male", "采用男性形象"), ("female", "采用女性形象"), ("other", "我变成了一只螃蟹"), ("unspecified", "梦中的自己没有明确形象")])
@pytest.mark.parametrize("subject_matches", [True, False, "unavailable"])
def test_image_generation_is_submitted_once_then_polled(tmp_path: Path, appearance, expected, subject_matches):
    models = ImageModels()
    def review_subject(image_url, form):
        if subject_matches == "unavailable":
            from app.services.aliyun import ModelServiceError
            raise ModelServiceError("subject_review_unavailable")
        return subject_matches
    models.review_subject = review_subject
    settings = Settings(
        _env_file=None,
        DREAMCARD_ENV="test",
        DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
    )
    cards = LocalOriginalKnowledgeRetriever([
        OriginalKnowledgeCard(
            card_id="DREAM-001", title="鹿", aliases=(), retrieval_terms=("鹿",),
            category="动物", scope_note="scope", original_interpretation="text",
            reflection_prompts=(), gentle_actions=(), safety_note="safe",
            rights_status="original_pending_review", status="draft", source_file="test.md",
        )
    ])
    client = TestClient(create_app(
        settings=settings,
        models=models,
        original_knowledge_retriever=cards,
    ))
    created = client.post("/api/v1/dreams/extract", json={
        "dream_text": "我在森林里看见一只鹿。"
    }).json()
    symbols = created["symbols"]
    symbols["scenes"] = ["森林"]
    symbols["characters"] = ["鹿"]
    missing_choice = client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": {**symbols, "characters": ["我"]},
    })
    assert missing_choice.status_code == 422
    assert client.put(f"/api/v1/dreams/{created['id']}/symbols", json={"symbols": symbols, "character_appearance": "other", "character_form": "  "}).status_code == 422
    ready = client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": symbols,
        "character_appearance": appearance,
        "character_form": "我变成了一只螃蟹" if appearance == "other" else "",
        "clarification_answer": (created["clarification"] or {"options": [None]})["options"][0],
    })
    assert ready.status_code == 200
    assert ready.json()["character_appearance"] == appearance
    assert client.get(f"/api/v1/dreams/{created['id']}").json()["character_appearance"] == appearance
    assert client.post(f"/api/v1/dreams/{created['id']}/interpretation").status_code == 200

    submitted = client.post(f"/api/v1/dreams/{created['id']}/image")
    assert submitted.status_code == 200
    if appearance == "other" and subject_matches == "unavailable":
        assert submitted.json()["failure_reason"] == "subject_review_unavailable"
        assert client.post(f"/api/v1/dreams/{created['id']}/image?retry=true").status_code == 200
        assert models.image_submissions == 1
        regenerated = client.post(f"/api/v1/dreams/{created['id']}/image?retry=true&regenerate=true")
        assert regenerated.status_code == 200
        assert models.image_submissions == 2
        models.review_subject = lambda url, form: True
        reviewed = client.post(f"/api/v1/dreams/{created['id']}/image/review")
        assert reviewed.json()["status"] == "completed"
        assert models.image_submissions == 2
        return
    if appearance == "other" and not subject_matches:
        assert submitted.json()["status"] == "completed"
        assert models.image_submissions == 1
        assert client.post(f"/api/v1/dreams/{created['id']}/image?retry=true&regenerate=true").status_code == 200
        assert "本次重绘重点" in models.last_prompt
        assert expected in models.last_prompt
        completed = client.get(f"/api/v1/dreams/{created['id']}/image").json()
        assert completed["status"] == "completed"
        assert completed["failure_reason"] == "subject_mismatch"
        assert completed["image_url"].endswith("/image/file")
        for _ in range(3):
            client.get(f"/api/v1/dreams/{created['id']}/image")
            client.post(f"/api/v1/dreams/{created['id']}/image?retry=true&regenerate=true")
        assert models.image_submissions == 2
        return
    assert submitted.json()["status"] == "completed"
    assert models.image_submissions == 1
    assert expected in models.last_prompt

    completed = client.get(f"/api/v1/dreams/{created['id']}/image")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["image_url"].endswith("/image/file")
    assert models.polls == 1

    repeat = client.post(f"/api/v1/dreams/{created['id']}/image")
    assert repeat.status_code == 200
    assert repeat.json()["status"] == "completed"
    assert models.image_submissions == 1

    interpretation_before = client.get(f"/api/v1/dreams/{created['id']}/interpretation").json()
    regenerated = client.post(f"/api/v1/dreams/{created['id']}/image?retry=true")
    assert regenerated.status_code == 200
    assert regenerated.json()["status"] == "completed"
    assert models.image_submissions == 1
    assert client.get(f"/api/v1/dreams/{created['id']}/interpretation").json() == interpretation_before


@pytest.mark.parametrize("band,always,panels", [(False, False, False), (True, False, False), (True, True, False), (False, False, True), (False, True, True)])
def test_quality_warning_waits_for_user_confirmed_regeneration(tmp_path: Path, band, always, panels):
    models = ImageModels()
    reviewer = RejectOnceReviewer(band=band, always=always, panels=panels)
    settings = Settings(
        _env_file=None,
        DREAMCARD_ENV="test",
        DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
    )
    cards = LocalOriginalKnowledgeRetriever([
        OriginalKnowledgeCard(
            card_id="DREAM-001", title="鹿", aliases=(), retrieval_terms=("鹿",),
            category="动物", scope_note="scope", original_interpretation="text",
            reflection_prompts=(), gentle_actions=(), safety_note="safe",
            rights_status="original_pending_review", status="draft", source_file="test.md",
        )
    ])
    client = TestClient(create_app(
        settings=settings,
        models=models,
        image_reviewer=reviewer,
        original_knowledge_retriever=cards,
    ))
    created = client.post("/api/v1/dreams/extract", json={
        "dream_text": "我在森林里看见一只鹿。"
    }).json()
    symbols = created["symbols"]
    symbols["scenes"] = ["森林"]
    symbols["characters"] = ["鹿"]
    ready = client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": symbols,
        "character_appearance": "unspecified",
        "clarification_answer": (created["clarification"] or {"options": [None]})["options"][0],
    })
    assert ready.status_code == 200
    assert client.post(f"/api/v1/dreams/{created['id']}/interpretation").status_code == 200

    submitted = client.post(f"/api/v1/dreams/{created['id']}/image")
    assert submitted.status_code == 200
    assert submitted.json()["status"] == "completed"
    assert submitted.json()["image_url"]
    if panels:
        assert submitted.json()["failure_reason"] == "contains_panels"
        assert submitted.json()["recovery_action"] == "retry_generation"
        # A flagged asset must remain downloadable, even without a variant query.
        from app.storage.repository import DreamRepository
        repo = DreamRepository(settings.database_path)
        repo.save_image_asset(created['id'], ready.json()['revision'], 'https://example.com/result.png', b'fixture-image', 'image/png')
        download = client.get(f"/api/v1/dreams/{created['id']}/image/file")
        assert download.status_code == 200 and download.content == b'fixture-image'
    assert models.image_submissions == 1
    assert reviewer.reviews == 1
    client.get(f"/api/v1/dreams/{created['id']}/image")
    client.post(f"/api/v1/dreams/{created['id']}/image?retry=true")
    assert models.image_submissions == 1
    assert client.post(f"/api/v1/dreams/{created['id']}/image?retry=true&regenerate=true").status_code == 200

    completed = client.get(f"/api/v1/dreams/{created['id']}/image")
    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    if always:
        assert completed.json()["failure_reason"] == ("contains_panels" if panels else "contains_band")
        assert completed.json()["image_url"]
        client.get(f"/api/v1/dreams/{created['id']}/image")
    assert models.image_submissions == 2
    assert reviewer.reviews == 2
    assert models.polls == 2


def test_failed_quality_retry_submission_does_not_poll_forever(tmp_path: Path):
    models = RetrySubmissionFailsModels()
    reviewer = RejectOnceReviewer()
    settings = Settings(
        _env_file=None,
        DREAMCARD_ENV="test",
        DREAMCARD_MODEL_MODE="mock",
        DREAMCARD_DATABASE_PATH=tmp_path / "test.db",
        DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE="local",
    )
    cards = LocalOriginalKnowledgeRetriever([
        OriginalKnowledgeCard(
            card_id="DREAM-001", title="鹿", aliases=(), retrieval_terms=("鹿",),
            category="动物", scope_note="scope", original_interpretation="text",
            reflection_prompts=(), gentle_actions=(), safety_note="safe",
            rights_status="original_pending_review", status="draft", source_file="test.md",
        )
    ])
    client = TestClient(create_app(
        settings=settings,
        models=models,
        image_reviewer=reviewer,
        original_knowledge_retriever=cards,
    ))
    created = client.post("/api/v1/dreams/extract", json={
        "dream_text": "我在森林里看见一只鹿。"
    }).json()
    symbols = created["symbols"]
    symbols["scenes"] = ["森林"]
    symbols["characters"] = ["鹿"]
    assert client.put(f"/api/v1/dreams/{created['id']}/symbols", json={
        "symbols": symbols,
        "character_appearance": "unspecified",
        "clarification_answer": (created["clarification"] or {"options": [None]})["options"][0],
    }).status_code == 200
    assert client.post(f"/api/v1/dreams/{created['id']}/interpretation").status_code == 200

    result = client.post(f"/api/v1/dreams/{created['id']}/image")
    assert result.status_code == 200
    assert result.json()["status"] == "completed"
    assert models.image_submissions == 1
    assert client.post(f"/api/v1/dreams/{created['id']}/image?retry=true&regenerate=true").status_code == 503
    assert models.image_submissions == 2

    polled = client.get(f"/api/v1/dreams/{created['id']}/image")
    assert polled.status_code == 200
    assert polled.json()["status"] == "completed"
    assert polled.json()["image_url"]


def test_variants_persist_and_are_account_isolated(tmp_path):
    import io
    from PIL import Image
    from app.storage.repository import DreamRepository
    from app.services.invite_auth import COOKIE
    models = ImageModels()
    models.get_image_task = lambda task_id: ImageTask(task_id=task_id, status='SUCCEEDED', image_urls=[f'https://example.com/{models.image_submissions}.png'])
    client, sid = prepared_image_client(tmp_path, models, RejectOnceReviewer(always=True), authenticated=True)
    repo = DreamRepository(tmp_path / 'test.db')
    revision = repo.get(sid).revision
    # Supply local provider assets without any network/image-model call.
    first_bytes = io.BytesIO()
    Image.new('RGB', (4, 4), 'blue').save(first_bytes, format='PNG')
    second_bytes = io.BytesIO()
    Image.new('RGB', (4, 4), 'green').save(second_bytes, format='PNG')
    client.post(f'/api/v1/dreams/{sid}/image')
    repo.save_image_asset(sid, revision, 'https://example.com/1.png', first_bytes.getvalue(), 'image/png')
    first = client.get(f'/api/v1/dreams/{sid}/image').json()
    assert first['status'] == 'completed' and len(first['variants']) == 1
    assert client.get(first['image_url']).content == first_bytes.getvalue()
    assert models.image_submissions == 1
    client.post(f'/api/v1/dreams/{sid}/image?retry=true&regenerate=true')
    repo.save_image_asset(sid, revision, 'https://example.com/2.png', second_bytes.getvalue(), 'image/png')
    second = client.get(f'/api/v1/dreams/{sid}/image').json()
    assert second['status'] == 'completed' and len(second['variants']) == 2
    assert client.get(second['image_url']).content == second_bytes.getvalue()
    chosen = client.post(f"/api/v1/dreams/{sid}/image/select/{first['selected_variant']}").json()
    assert client.get(chosen['image_url']).content == first_bytes.getvalue()
    assert DreamRepository(tmp_path / 'test.db').selected_image(sid, revision) == first['selected_variant']
    assert client.get(f'/api/v1/dreams/{sid}/image').json()['selected_variant'] == first['selected_variant']
    assert client.get('/api/v1/account/quota').json()['used'] == 1
    client.post(f'/api/v1/dreams/{sid}/image?retry=true&regenerate=true')
    assert models.image_submissions == 2
    assert client.post(f'/api/v1/dreams/{sid}/image/select/not-owned').status_code == 404
    _, other_code = client.app.state.invite_auth.issue()
    other = TestClient(client.app)
    other.post('/api/v1/auth/login', json={'invite_code': other_code})
    assert other.get(chosen['image_url']).status_code == 404
    assert other.post(f"/api/v1/dreams/{sid}/image/select/{first['selected_variant']}").status_code == 404


def test_late_fox_supplement_is_preserved_as_visual_prose():
    form = '我是一只巴掌大的红色狐狸，四只脚、蓬松的大尾巴，没有人类身体，也不穿衣服。我用嘴叼着那封信'
    session = DreamSessionResponse(id='fox', status='ready_to_generate', revision=1, model_mode='mock', created_at='test', updated_at='test',
        dream_text='我在邮局收到一封信，里面写着“不要让钟声看见你”。',
        character_appearance='other', character_form=form,
        symbols=DreamSymbols(scenes=['云下邮局'], characters=['没有影子的邮递员'], objects=['信封'], relationships=['邮递员递给我信', '信里只有一句话']))
    draft = ImageModels().chat_json(None, None, None, PersonalizedInterpretationDraft)
    for retry in (False, True):
        prompt = image_prompt(session, draft, retry_without_text=retry)
        assert form in prompt and '邮递员递给我信' in prompt
        assert '没有影子的邮递员' in prompt and '空白无字' in prompt
        assert '不要让钟声看见你' not in prompt
        assert not any(field in prompt for field in ['scenes', 'relationships', '角色编号', 'JSON', 'dreamer'])
        assert len(prompt) < 3000
