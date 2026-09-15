import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from threading import Event, Thread
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.core.config import Settings
from app.core.request_logging import install_request_logging
from app.schemas.dream import (
    DeleteResponse,
    DreamImageResponse,
    DreamSessionResponse,
    DreamSymbols,
    ExtractDreamRequest,
    UpdateSymbolsRequest,
)
from app.services.extractor import DreamExtractor
from app.services.aliyun import AliyunModels, ImageTask, ModelServiceError
from app.services.interpretation import (
    InterpretationGenerationResponse,
    InterpretationSource,
    PersonalizedInterpretationDraft,
    SourcePassage,
    draft_personalized_interpretation,
    draft_interpretation,
    image_prompt,
)
from app.services.image_quality import (
    AllowAllImageReviewer,
    ImageQualityResult,
    LocalImageQualityReviewer,
)
from app.services.moderation import TextModerator, ModerationError
from app.services.original_knowledge import LocalOriginalKnowledgeRetriever
from app.services.retrieval import DreamRetrievalService
from app.storage.repository import DreamRepository
from app.services.invite_auth import install_invite_auth
from app.services.zhihu_auth import install_zhihu_auth


CRISIS_TERMS = ("自杀", "不想活", "结束生命", "伤害自己", "活不下去")
SAFETY_MESSAGE = "你描述的内容可能涉及正在承受的危机。梦卡先暂停普通解读，请优先联系身边可信任的人或当地紧急支持服务。"
logger = logging.getLogger(__name__)


def error_response(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def create_app(
    settings: Settings | None = None,
    database_path: Path | None = None,
    models: AliyunModels | None = None,
    retrieval_service: DreamRetrievalService | None = None,
    original_knowledge_retriever: LocalOriginalKnowledgeRetriever | None = None,
    image_reviewer: LocalImageQualityReviewer | AllowAllImageReviewer | None = None,
) -> FastAPI:
    app_settings = settings or Settings()
    if database_path is not None:
        app_settings.database_path = database_path
    repository = DreamRepository(app_settings.database_path)
    extractor = DreamExtractor(app_settings)
    moderator = TextModerator(app_settings)
    generation_models = models or AliyunModels(app_settings)
    artwork_reviewer = image_reviewer or (
        LocalImageQualityReviewer(app_settings.model_timeout_seconds)
        if models is None
        else AllowAllImageReviewer()
    )
    uses_local_image_reviewer = models is None and image_reviewer is None
    retrieval = retrieval_service or DreamRetrievalService(
        app_settings, models=generation_models
    )
    shadow_load_status = "disabled"
    shadow_retriever = original_knowledge_retriever
    if app_settings.original_knowledge_shadow_mode == "local":
        if shadow_retriever is None:
            try:
                shadow_retriever = LocalOriginalKnowledgeRetriever.from_jsonl(
                    app_settings.original_knowledge_cards_path
                )
            except (OSError, ValueError, KeyError, TypeError):
                shadow_load_status = "cards_unavailable"
                logger.warning("original knowledge shadow cards are unavailable")
        if shadow_retriever is not None:
            shadow_load_status = "ready"

    production = app_settings.environment == "production"
    app = FastAPI(title="梦卡 API", version="0.1.0",
                  docs_url=None if production else "/docs",
                  redoc_url=None if production else "/redoc",
                  openapi_url=None if production else "/openapi.json")

    def moderate(text: str, direction: str) -> None:
        # Explicitly disabled keeps phase-one behaviour; it is NOT an audit pass.
        if app_settings.moderation_mode == "aliyun":
            moderator.require_allowed(text, direction)

    def run_original_knowledge_shadow(session: DreamSessionResponse) -> None:
        """Observe confirmed symbols only; shadow failures never affect the user flow."""
        if shadow_retriever is None or session.status != "ready_to_generate":
            return
        try:
            result = retrieve_original_knowledge(session)
            repository.record_original_knowledge_shadow(
                session_id=session.id,
                revision=session.revision,
                fallback=result.fallback,
                hits=[
                    {
                        "card_id": hit.card.card_id,
                        "role": hit.role,
                        "score": hit.score,
                        "matched_terms": list(hit.matched_terms),
                    }
                    for hit in result.hits
                ],
            )
        except Exception:
            # This is deliberately fail-open: shadow analytics must never block a
            # confirmed dream or alter its API response.
            logger.exception(
                "original knowledge shadow failed for session=%s revision=%s",
                session.id,
                session.revision,
            )

    def retrieve_original_knowledge(session: DreamSessionResponse):
        """Build a local query from confirmed fields only, never dream text."""
        if shadow_retriever is None:
            return None
        query_parts: list[str] = []
        symbol_groups = session.symbols.model_dump(
            exclude={"reality_context", "uncertain_fields"}
        )
        for values in symbol_groups.values():
            query_parts.extend(values)
        if session.clarification_answer:
            query_parts.append(session.clarification_answer)
        # One-character terms are only safe to retrieve when the user has
        # explicitly confirmed them as a character or object. Free text remains
        # protected from substring false positives such as 水果/海外.
        confirmed_single_character_terms = (
            symbol_groups[category] for category in ("characters", "objects")
        )
        return shadow_retriever.retrieve(
            " ".join(query_parts),
            confirmed_single_character_terms=(
                value for values in confirmed_single_character_terms for value in values
            ),
        )

    @app.exception_handler(ModerationError)
    async def moderation_exception_handler(_request: Request, error: ModerationError):
        if error.code == "content_review_required":
            return error_response(422, error.code, "这段内容需要进一步审核，暂时无法继续。你可以修改内容后重试。")
        if error.code == "moderation_text_too_long":
            return error_response(422, error.code, "内容超过当前审核长度限制，请精简后重试。")
        return error_response(503, "moderation_unavailable", "内容安全检查暂时不可用，请稍后重试。")

    @app.get("/api/v1/moderation/configuration")
    def moderation_configuration() -> dict:
        return moderator.configuration()
    install_invite_auth(app, app_settings)
    install_zhihu_auth(app, app_settings)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.parsed_cors_origins(),
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, _error: RequestValidationError
    ) -> JSONResponse:
        return error_response(422, "validation_error", "请检查输入后重试")

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "model_mode": app_settings.model_mode}

    @app.get("/api/v1/models/configuration")
    def model_configuration() -> dict:
        # Configuration presence is NOT a successful remote connectivity check.
        return {
            "provider": "aliyun",
            "model_mode": app_settings.model_mode,
            "api_key_configured": bool(app_settings.dashscope_api_key),
            "live_connection_verified": False,
            "models": {
                "extract": app_settings.qwen_extract_model,
                "interpret": app_settings.qwen_interpret_model,
                "embedding": app_settings.embedding_model,
                "rerank": app_settings.rerank_model,
                "image": app_settings.wan_image_model,
            },
            "generation_endpoint_available": bool(
                app_settings.model_mode == "aliyun"
                and app_settings.dashscope_api_key
                and app_settings.knowledge_index_path.is_file()
            ),
        }

    @app.get("/api/v1/knowledge/shadow/configuration")
    def original_knowledge_shadow_configuration() -> dict:
        return {
            "mode": app_settings.original_knowledge_shadow_mode,
            "status": shadow_load_status,
            "card_count": len(shadow_retriever.cards) if shadow_retriever else 0,
            "changes_user_output": False,
            "uses_cloud_model": False,
            "production_eligible": False,
        }

    @app.post("/api/v1/dreams/extract", response_model=DreamSessionResponse)
    def extract_dream(request: ExtractDreamRequest, http_request: Request) -> DreamSessionResponse | JSONResponse:
        if len(request.dream_text) > app_settings.max_dream_chars:
            return error_response(
                422,
                "dream_too_long",
                f"梦境内容暂时不能超过 {app_settings.max_dream_chars} 个字符",
            )
        if any(term in request.dream_text for term in CRISIS_TERMS):
            return repository.create(
                dream_text=request.dream_text,
                status="safety_interrupted",
                symbols=DreamSymbols(),
                clarification=None,
                model_mode=app_settings.model_mode,
                safety_message=SAFETY_MESSAGE,
                owner_id=http_request.state.account_id,
            )
        try:
            moderate(request.dream_text, "input")
            result = extractor.extract(request.dream_text)
            moderate(result.model_dump_json(), "output")
        except ModerationError:
            raise
        except ModelServiceError as error:
            logger.warning("dream extraction failed: %s", error.code)
            return error_response(503, "model_unavailable", "梦象提取暂时失败，请稍后重试")
        except RuntimeError:
            return error_response(503, "model_unavailable", "梦象提取暂时失败，请稍后重试")
        return repository.create(
            dream_text=request.dream_text,
            status="reviewing_symbols",
            owner_id=http_request.state.account_id,
            symbols=result.symbols,
            clarification=result.clarification,
            model_mode=app_settings.model_mode,
        )

    @app.get("/api/v1/dreams/{session_id}", response_model=DreamSessionResponse)
    def get_dream(session_id: str) -> DreamSessionResponse | JSONResponse:
        try:
            return repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        except RuntimeError:
            return error_response(500, "storage_error", "会话数据异常，请重新开始")

    @app.put("/api/v1/dreams/{session_id}/symbols", response_model=DreamSessionResponse)
    def update_symbols(
        session_id: str, request: UpdateSymbolsRequest
    ) -> DreamSessionResponse | JSONResponse:
        try:
            # Validate existence/state before spending a review request.
            current = repository.get(session_id)
            if current.status not in ("reviewing_symbols", "awaiting_clarification", "ready_to_generate"):
                return error_response(409, "invalid_state", "当前梦境无法继续这一步")
            if request.character_appearance is None:
                return error_response(422, "character_appearance_required", "请先选择梦中自己的形态，也可以选择没有明确形象")
            if request.character_appearance == "other" and not request.character_form.strip():
                return error_response(422, "character_form_required", "请描述梦中自己的形态，例如：我变成了一只螃蟹")
            # The selected appearance is the sole confirmed subject, not a second
            # independent answer alongside extraction candidates.
            request.symbols.dreamer = [request.character_form.strip() if request.character_appearance == "other" else {
                "male": "男性形象", "female": "女性形象", "unspecified": "没有明确形象", "none": "没有明确形象",
            }[request.character_appearance]]
            moderate(request.model_dump_json(), "input")
            updated = repository.update_symbols(
                session_id=session_id,
                symbols=request.symbols,
                clarification_answer=request.clarification_answer,
                character_appearance=request.character_appearance or "unspecified",
                character_form=request.character_form.strip() if request.character_appearance == "other" else "",
            )
            run_original_knowledge_shadow(updated)
            return updated
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        except ValueError:
            return error_response(409, "invalid_state", "当前梦境无法继续这一步")
        except ModerationError:
            raise
        except RuntimeError:
            return error_response(500, "storage_error", "会话数据异常，请重新开始")

    def generation_error(record: dict) -> JSONResponse:
        code = record.get("error_code") or "generation_failed"
        if code == "generation_interrupted":
            return error_response(409, code, "上次解读已中断，梦境内容已保留，请重新开始解析。")
        if code == "content_review_required":
            return error_response(422, code, "生成内容需要进一步审核，暂时无法展示。")
        return error_response(503, "generation_failed", "梦境解读生成失败，请修改梦象后再试。")

    def base_image_response(session_id: str, revision: int, record: dict) -> DreamImageResponse:
        attempts = record.get('quality_retry_count', 0)
        retained_failure = record.get("error_code")
        if retained_failure in ("subject_mismatch", "subject_review_unavailable", "image_review_unavailable") and record.get("image_url"):
            return DreamImageResponse(session_id=session_id, revision=revision, status="completed", image_url=f"/api/v1/dreams/{session_id}/image/file", failure_reason=retained_failure, supplementary_attempts=attempts, recovery_action='retry_review' if retained_failure != 'subject_mismatch' else None)
        if record["status"] == "completed":
            return DreamImageResponse(
                session_id=session_id,
                revision=revision,
                status="completed",
                image_url=f"/api/v1/dreams/{session_id}/image/file",
                supplementary_attempts=attempts,
            )
        if record["status"] == "failed":
            return DreamImageResponse(
                session_id=session_id,
                revision=revision,
                status="failed",
                supplementary_attempts=attempts,
                recovery_action=(
                    'contact_support' if retained_failure == 'submission_unknown'
                    else 'check_task' if retained_failure == 'generation_timeout'
                    else 'retry_generation' if attempts < 1 else 'contact_support'
                ),
                failure_reason=(
                    "contains_text"
                    if record.get("error_code") == "image_contains_text"
                    else "contains_band" if record.get("error_code") == "image_contains_band"
                    else "contains_panels" if record.get("error_code") == "image_contains_panels"
                    else record["error_code"] if record.get("error_code") in ("subject_mismatch", "subject_review_unavailable", "image_review_unavailable", "generation_timeout", "submission_unknown", "prompt_too_long")
                    else "generation_failed"
                ),
            )
        return DreamImageResponse(
            session_id=session_id,
            revision=revision,
            status="pending" if not record.get("task_id") else "processing",
            retry_after_seconds=3,
            supplementary_attempts=attempts,
        )

    def image_response(session_id: str, revision: int, record: dict) -> DreamImageResponse:
        result = base_image_response(session_id, revision, record)
        variants = repository.image_variants(session_id, revision)
        selected = repository.selected_image(session_id, revision)
        selected = selected if selected in variants else (variants[-1] if variants else None)
        result.variants = variants
        result.selected_variant = selected
        if selected:
            result.image_url = f"/api/v1/dreams/{session_id}/image/file?variant={selected}"
        elif record.get("image_url"):
            result.image_url = f"/api/v1/dreams/{session_id}/image/file"
        if result.image_url:
            if record["status"] != "processing":
                result.status = "completed"
            if record.get("error_code") == "image_contains_text":
                result.failure_reason = "contains_text"
            elif record.get("error_code") == "image_contains_band":
                result.failure_reason = "contains_band"
            elif record.get("error_code") == "image_contains_panels":
                result.failure_reason = "contains_panels"
            if record.get("error_code") in ("image_contains_text", "image_contains_band", "image_contains_panels", "subject_mismatch", "subject_review_unavailable", "image_review_unavailable"):
                result.recovery_action = "retry_generation" if result.supplementary_attempts < 1 else None
        return result


    def stored_interpretation(session_id: str, revision: int) -> InterpretationGenerationResponse | None:
        record = repository.get_generation(session_id, revision)
        if record is None or record["status"] != "completed":
            return None
        try:
            return InterpretationGenerationResponse.model_validate_json(record["result_json"])
        except (ValueError, TypeError):
            raise RuntimeError("解读数据异常") from None

    def image_age_seconds(record: dict) -> float:
        try:
            return max(0.0, (datetime.now(UTC) - datetime.fromisoformat(record["updated_at"])).total_seconds())
        except (KeyError, TypeError, ValueError):
            return 0.0

    def download_provider_image(image_url: str) -> tuple[bytes, str]:
        parsed = urlparse(image_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
            raise ModelServiceError("image_review_invalid_url")
        try:
            with httpx.Client(timeout=app_settings.model_timeout_seconds, follow_redirects=False) as client:
                response = client.get(image_url)
        except httpx.HTTPError:
            raise ModelServiceError("image_review_unavailable") from None
        media_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
        if response.status_code != 200 or not media_type.startswith("image/") or len(response.content) > 12 * 1024 * 1024:
            raise ModelServiceError("image_review_unavailable")
        return response.content, media_type

    def review_candidate(session: DreamSessionResponse, image_url: str) -> ImageQualityResult | None:
        try:
            if uses_local_image_reviewer and isinstance(artwork_reviewer, LocalImageQualityReviewer):
                try:
                    asset = repository.get_image_asset(session.id, session.revision, image_url)
                except Exception:
                    logger.exception("stored image read failed for session=%s", session.id)
                    asset = None
                if asset is None:
                    content, media_type = download_provider_image(image_url)
                    try:
                        repository.save_image_asset(session.id, session.revision, image_url, content, media_type)
                    except Exception:
                        # Local persistence is a recovery layer. A disk issue
                        # must not turn an otherwise valid provider result into
                        # a failed generation.
                        logger.exception("stored image write failed for session=%s", session.id)
                else:
                    content = asset["content"]
                return artwork_reviewer.review_bytes(content)
            return artwork_reviewer.review_url(image_url)
        except ModelServiceError as error:
            logger.warning("image quality review failed for %s: %s", session.id, error.code)
            repository.image_event(session.id, session.revision, "quality_review_error", code=error.code, request_id=error.request_id)
            repository.fail_image_generation(session.id, session.revision, "image_review_unavailable")
            return None

    def refresh_image_generation_unlocked(
        session: DreamSessionResponse, record: dict, review_only: bool = False
    ) -> DreamImageResponse:
        if record["status"] == "processing" and not record.get("task_id"):
            # A quality retry is claimed before its provider task is submitted.
            # If submission failed or the process stopped in that gap, never
            # leave the browser polling a task that cannot make progress.
            if record.get("quality_retry_count", 0) > 0 and image_age_seconds(record) >= 120:
                repository.fail_image_generation(
                    session.id, session.revision, "submission_unknown"
                )
                refreshed = repository.get_image_generation(session.id, session.revision)
                if refreshed is None:
                    raise RuntimeError("图片任务状态丢失")
                return image_response(session.id, session.revision, refreshed)
            if image_age_seconds(record) >= 120:
                repository.fail_image_generation(session.id, session.revision, "submission_unknown")
                return image_response(session.id, session.revision, repository.get_image_generation(session.id, session.revision))
            return image_response(session.id, session.revision, record)
        if record["status"] != "processing":
            return image_response(session.id, session.revision, record)
        if not review_only and image_age_seconds(record) >= app_settings.image_wait_seconds:
            repository.fail_image_generation(session.id, session.revision, "generation_timeout")
            return image_response(session.id, session.revision, repository.get_image_generation(session.id, session.revision))
        try:
            if review_only and record.get("image_url"):
                task = ImageTask(task_id=record["task_id"], status="SUCCEEDED", image_urls=[record["image_url"]])
            else:
                task = generation_models.get_image_task(record["task_id"])
            if task.status == "SUCCEEDED":
                image_url = str(task.image_urls[0])
                repository.retain_image_candidate(session.id, session.revision, image_url)
                review = review_candidate(session, image_url)
                if review is None:
                    return image_response(session.id, session.revision, repository.get_image_generation(session.id, session.revision))
                if review.accepted and session.character_appearance == "other":
                    try:
                        subject_ok = generation_models.review_subject(image_url, session.character_form)
                    except ModelServiceError as error:
                        logger.warning("subject review failed for %s: %s", session.id, error.code)
                        repository.fail_image_generation(session.id, session.revision, "subject_review_unavailable")
                        return image_response(session.id, session.revision, repository.get_image_generation(session.id, session.revision))
                    if not subject_ok:
                        repository.fail_image_generation(session.id, session.revision, "subject_mismatch")
                        return image_response(session.id, session.revision, repository.get_image_generation(session.id, session.revision))
                if review.accepted:
                    repository.complete_image_generation(
                        session.id, session.revision, image_url
                    )
                else:
                    repository.fail_image_generation(
                        session.id, session.revision,
                        "image_contains_panels" if review.contains_panels else "image_contains_band" if review.contains_band else "image_contains_text"
                    )
            elif task.status in ("FAILED", "CANCELED", "UNKNOWN"):
                repository.image_event(session.id, session.revision, "provider_failed", code=task.provider_code or task.status, request_id=task.request_id, task_id=task.task_id)
                repository.fail_image_generation(session.id, session.revision, "image_task_failed")
        except ModelServiceError as error:
            # A transient provider read error should not discard a task that can
            # still finish remotely; only terminal task states become failures.
            logger.warning("image polling failed: %s", error.code)
            repository.image_event(session.id, session.revision, "poll_error", code=error.provider_code or error.code, request_id=error.request_id, task_id=record.get("task_id"))
        refreshed = repository.get_image_generation(session.id, session.revision)
        if refreshed is None:
            raise RuntimeError("图片任务状态丢失")
        return image_response(session.id, session.revision, refreshed)

    def refresh_image_generation(
        session: DreamSessionResponse, record: dict, review_only: bool = False
    ) -> DreamImageResponse:
        token = repository.claim_image_lease(session.id, session.revision)
        if token is None:
            current = repository.get_image_generation(session.id, session.revision)
            return image_response(session.id, session.revision, current or record)
        try:
            current = repository.get_image_generation(session.id, session.revision) or record
            return refresh_image_generation_unlocked(session, current, review_only)
        finally:
            repository.release_image_lease(session.id, session.revision, token)

    @app.get(
        "/api/v1/dreams/{session_id}/interpretation",
        response_model=InterpretationGenerationResponse,
    )
    def get_interpretation(session_id: str) -> InterpretationGenerationResponse | JSONResponse:
        try:
            current = repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        repository.expire_generation(session_id, current.revision)
        record = repository.get_generation(session_id, current.revision)
        if record is None:
            return error_response(404, "interpretation_not_found", "这次梦境还没有生成解读")
        if record["status"] == "processing":
            return error_response(409, "generation_in_progress", "梦境解读正在生成")
        if record["status"] == "failed":
            return generation_error(record)
        try:
            return InterpretationGenerationResponse.model_validate_json(record["result_json"])
        except (ValueError, TypeError):
            return error_response(500, "storage_error", "解读数据异常，请重新开始")

    @app.post(
        "/api/v1/dreams/{session_id}/interpretation",
        response_model=InterpretationGenerationResponse,
    )
    def generate_interpretation(
        session_id: str, retry: bool = False
    ) -> InterpretationGenerationResponse | JSONResponse:
        try:
            current = repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        except RuntimeError:
            return error_response(500, "storage_error", "会话数据异常，请重新开始")
        if current.status != "ready_to_generate":
            return error_response(409, "symbols_not_confirmed", "请先确认梦象后再生成解读")

        repository.expire_generation(session_id, current.revision)
        existing = repository.get_generation(session_id, current.revision)
        if existing is not None:
            if existing["status"] == "completed":
                try:
                    return InterpretationGenerationResponse.model_validate_json(
                        existing["result_json"]
                    )
                except (ValueError, TypeError):
                    return error_response(500, "storage_error", "解读数据异常，请重新开始")
            if existing["status"] == "processing":
                return error_response(409, "generation_in_progress", "梦境解读正在生成")
            if not retry:
                return generation_error(existing)
            if not repository.retry_generation(session_id, current.revision):
                return error_response(409, "generation_in_progress", "梦境解读正在生成")
        elif not repository.begin_generation(session_id, current.revision):
            return error_response(409, "generation_in_progress", "梦境解读正在生成")

        started_at = repository.get_generation(session_id, current.revision)["updated_at"]
        try:
            original_knowledge_result = retrieve_original_knowledge(current)
            # 本地梦象卡仍处于草稿观察期。所有已确认梦境均走同一套完整的
            # 专属回望生成；卡片命中仅用于匿名评估，不进入未完成审核的英文引文链。
            if original_knowledge_result is not None:
                draft: InterpretationDraft | PersonalizedInterpretationDraft = (
                    draft_personalized_interpretation(
                        current,
                        generation_models,
                        original_knowledge_result.hits,
                    )
                )
                moderate(draft.model_dump_json(), "output")
                response = InterpretationGenerationResponse(
                    session_id=session_id,
                    revision=current.revision,
                    review_status="passed" if app_settings.moderation_mode == "aliyun" else "not_enabled",
                    generation_mode="personalized",
                    interpretation=draft,
                    sources=[],
                )
                repository.complete_generation(
                    session_id, current.revision, response.model_dump_json(), started_at=started_at
                )
                return response

            retrieval_result = retrieval.retrieve(current.symbols, current.clarification_answer)
            passages = [SourcePassage(
                id=source.source_id,
                book=source.book,
                location=f"{source.chapter} lines {source.source_line_start}-{source.source_line_end}",
                text=source.original_text,
            ) for source in retrieval_result.passages]
            draft = draft_interpretation(current, passages, generation_models)
            moderate(draft.model_dump_json(), "output")
            response = InterpretationGenerationResponse(
                session_id=session_id,
                revision=current.revision,
                review_status="passed" if app_settings.moderation_mode == "aliyun" else "not_enabled",
                interpretation=draft,
                sources=[InterpretationSource(
                    source_id=source.source_id, book=source.book, author=source.author,
                    translator=source.translator, chapter=source.chapter,
                    source_url=source.source_url, source_line_start=source.source_line_start,
                    source_line_end=source.source_line_end,
                    source_file_sha256=source.source_file_sha256,
                    rights_status=source.rights_status, verified=source.verified,
                    rerank_score=source.rerank_score,
                ) for source in retrieval_result.passages],
            )
            repository.complete_generation(session_id, current.revision, response.model_dump_json(), started_at=started_at)
            return response
        except ModerationError as error:
            repository.fail_generation(session_id, current.revision, error.code, started_at=started_at)
            raise
        except ModelServiceError as error:
            repository.fail_generation(session_id, current.revision, error.code, started_at=started_at)
            return error_response(503, "generation_failed", "梦境解读生成失败，请修改梦象后再试。")
        except (RuntimeError, ValueError):
            repository.fail_generation(session_id, current.revision, "generation_internal_error", started_at=started_at)
            return error_response(503, "generation_failed", "梦境解读生成失败，请修改梦象后再试。")

    @app.post("/api/v1/dreams/{session_id}/image", response_model=DreamImageResponse)
    def generate_dream_image(session_id: str, request: Request, retry: bool = False, regenerate: bool = False) -> DreamImageResponse | JSONResponse:
        try:
            current = repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        if current.status != "ready_to_generate":
            return error_response(409, "symbols_not_confirmed", "请先确认梦象后再生成图片")
        try:
            interpretation = stored_interpretation(session_id, current.revision)
        except RuntimeError:
            return error_response(500, "storage_error", "解读数据异常，请重新开始")
        if interpretation is None:
            return error_response(409, "interpretation_not_ready", "请先生成梦境解读")

        existing = repository.get_image_generation(session_id, current.revision)
        if existing is not None:
            if existing.get('error_code') in ('submission_unknown', 'generation_timeout'):
                return image_response(session_id, current.revision, existing)
            if existing.get("image_url") and not (retry and regenerate):
                return image_response(session_id, current.revision, existing)
            if existing["status"] == "completed":
                return image_response(session_id, current.revision, existing)
            if existing["status"] == "processing":
                return refresh_image_generation(current, existing)
            if not retry:
                return error_response(503, "image_generation_failed", "梦境图像生成失败，请稍后重试")
            if existing.get('quality_retry_count', 0) >= 1:
                return image_response(session_id, current.revision, existing)
            if app_settings.auth_enabled and not app.state.invite_auth.reserve_image(request.state.account_id, session_id, current.revision):
                return error_response(403, "image_quota_exhausted", "额度不足")
            if not repository.retry_image_generation(session_id, current.revision):
                return error_response(409, "image_generation_in_progress", "梦境图像正在生成")
        else:
            if app_settings.auth_enabled and not app.state.invite_auth.reserve_image(request.state.account_id, session_id, current.revision):
                return error_response(403, "image_quota_exhausted", "额度不足")
            if not repository.begin_image_generation(session_id, current.revision):
                return error_response(409, "image_generation_in_progress", "梦境图像正在生成")

        try:
            reason = existing.get("error_code") if existing else None
            prompt = image_prompt(current, interpretation.interpretation,
                                  retry_subject=reason == "subject_mismatch",
                                  retry_without_text=reason == "image_contains_text",
                                  retry_without_band=reason in ("image_contains_band", "image_contains_panels"))
            moderate(prompt, "output")
            task = generation_models.submit_image(prompt)
            repository.attach_image_task(session_id, current.revision, task.task_id)
            record = repository.get_image_generation(session_id, current.revision)
            if record is None:
                raise RuntimeError("图片任务状态丢失")
            return refresh_image_generation(current, record)
        except ModerationError as error:
            repository.fail_image_generation(session_id, current.revision, error.code)
            raise
        except ModelServiceError as error:
            failure_code = (
                "prompt_too_long" if error.code == "image_prompt_invalid"
                else "submission_unknown" if error.code in ("model_timeout", "model_connection_failed")
                else error.code
            )
            repository.image_event(session_id, current.revision, "submission_error", code=error.provider_code or error.code, request_id=error.request_id)
            repository.fail_image_generation(session_id, current.revision, failure_code)
            return error_response(503, "image_generation_failed", "梦境图像生成失败，请稍后重试")
        except RuntimeError:
            repository.fail_image_generation(session_id, current.revision, "image_generation_internal_error")
            return error_response(503, "image_generation_failed", "梦境图像生成失败，请稍后重试")

    @app.post("/api/v1/dreams/{session_id}/image/review", response_model=DreamImageResponse)
    def retry_dream_image_review(session_id: str) -> DreamImageResponse | JSONResponse:
        try:
            current = repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        previous = repository.get_image_generation(session_id, current.revision)
        if not repository.retry_image_review(session_id, current.revision):
            return error_response(409, "review_not_retryable", "当前图片不需要重试核验")
        return refresh_image_generation(current, repository.get_image_generation(session_id, current.revision), review_only=previous.get('error_code') != 'generation_timeout')

    @app.get("/api/v1/dreams/{session_id}/image", response_model=DreamImageResponse)
    def get_dream_image(session_id: str) -> DreamImageResponse | JSONResponse:
        try:
            current = repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        record = repository.get_image_generation(session_id, current.revision)
        if record is None:
            return error_response(404, "image_not_found", "这次梦境还没有生成图像")
        return refresh_image_generation(current, record)

    @app.get("/api/v1/dreams/{session_id}/image/file", response_model=None)
    def get_dream_image_file(session_id: str, variant: str | None = None) -> Response:
        """Proxy a completed provider image without storing it in a cloud bucket."""
        try:
            current = repository.get(session_id)
        except KeyError:
            return error_response(404, "not_found", "没有找到这次梦境记录")
        if variant:
            asset = repository.image_asset_by_hash(session_id, current.revision, variant)
            if asset is None:
                return error_response(404, "image_not_found", "没有找到这张图片")
            return Response(content=asset["content"], media_type=asset["media_type"])
        record = repository.get_image_generation(session_id, current.revision)
        image_url = record.get("image_url") if record else None
        parsed = urlparse(image_url or "")
        retained_codes = ("subject_mismatch", "subject_review_unavailable", "image_review_unavailable", "image_contains_text", "image_contains_band", "image_contains_panels", "image_task_failed", "generation_timeout", "submission_unknown")
        if record is None or (record["status"] != "completed" and record.get("error_code") not in retained_codes) or parsed.scheme != "https" or not parsed.netloc:
            return error_response(404, "image_not_ready", "梦境图像尚未准备完成")
        asset = repository.get_image_asset(session_id, current.revision, image_url)
        if asset is not None:
            return Response(content=asset["content"], media_type=asset["media_type"], headers={"Cache-Control": "private, max-age=3600"})
        try:
            content, content_type = download_provider_image(image_url)
            repository.save_image_asset(session_id, current.revision, image_url, content, content_type)
        except ModelServiceError:
            return error_response(503, "image_unavailable", "梦境图像暂时无法读取，请稍后重试")
        return Response(
            content=content,
            media_type=content_type,
            headers={"Cache-Control": "private, max-age=3600"},
        )

    @app.post("/api/v1/dreams/{session_id}/image/select/{variant}", response_model=DreamImageResponse)
    def select_dream_image(session_id: str, variant: str):
        current = repository.get(session_id)
        if not repository.select_image(session_id, current.revision, variant):
            return error_response(404, "image_not_found", "没有找到这张图片")
        return image_response(session_id, current.revision, repository.get_image_generation(session_id, current.revision))

    @app.delete("/api/v1/dreams/{session_id}", response_model=DeleteResponse)
    def delete_dream(session_id: str) -> DeleteResponse | JSONResponse:
        if not repository.delete(session_id):
            return error_response(404, "not_found", "没有找到这次梦境记录")
        return DeleteResponse(deleted=True)

    worker_stop = Event()

    def image_worker() -> None:
        while not worker_stop.wait(3):
            for session_id, revision in repository.pending_images():
                try:
                    current = repository.get(session_id)
                    if current.revision != revision:
                        continue
                    record = repository.get_image_generation(session_id, revision)
                    if record is not None:
                        refresh_image_generation(current, record)
                except Exception:
                    logger.exception("background image refresh failed for session=%s revision=%s", session_id, revision)

    @app.on_event("startup")
    def start_image_worker() -> None:
        if app_settings.image_worker_enabled and app_settings.environment != "test":
            Thread(target=image_worker, name="dreamcard-image-worker", daemon=True).start()

    @app.on_event("shutdown")
    def stop_image_worker() -> None:
        worker_stop.set()

    install_request_logging(app)
    return app


app = create_app()
