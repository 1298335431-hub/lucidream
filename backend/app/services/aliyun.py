"""Alibaba Cloud wire adapter. No mock fallback, logging of payloads, or hidden polling."""

import json
import math
import re
from typing import Literal, TypeVar

import httpx
from pydantic import BaseModel, Field, HttpUrl, ValidationError, model_validator

from app.core.config import Settings


T = TypeVar("T", bound=BaseModel)


class ModelServiceError(RuntimeError):
    """Safe codes only: never expose provider response bodies or credentials."""

    def __init__(self, code: str, request_id: str | None = None, provider_code: str | None = None):
        self.code = code
        self.request_id = request_id
        self.provider_code = provider_code
        super().__init__(code)


class ImageTask(BaseModel):
    task_id: str = Field(min_length=1)
    status: Literal["PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELED", "UNKNOWN"]
    image_urls: list[HttpUrl] = Field(default_factory=list)
    # These are temporary, unaudited provider outputs, not downloadable dream cards.
    review_status: Literal["pending"] = "pending"
    request_id: str | None = None
    provider_code: str | None = None

    @model_validator(mode="after")
    def require_image_on_success(self):
        if self.status == "SUCCEEDED" and not self.image_urls:
            raise ValueError("Successful image task has no image")
        return self


class EmbeddingBatch(BaseModel):
    vectors: list[list[float]] = Field(min_length=1, max_length=10)
    model: str = Field(min_length=1)
    total_tokens: int = Field(ge=0)


class RerankItem(BaseModel):
    index: int = Field(ge=0)
    relevance_score: float = Field(ge=0, le=1)


class RerankBatch(BaseModel):
    results: list[RerankItem] = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1)
    total_tokens: int = Field(ge=0)


class AliyunModels:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    def _request(self, method: str, path: str, payload: dict | None = None,
                 *, asynchronous: bool = False) -> dict:
        if self.settings.model_mode != "aliyun":
            raise ModelServiceError("aliyun_mode_required")
        if not self.settings.dashscope_api_key:
            raise ModelServiceError("api_key_missing")
        headers = {"Authorization": f"Bearer {self.settings.dashscope_api_key}"}
        if asynchronous:
            headers["X-DashScope-Async"] = "enable"
        try:
            # No automatic POST retry: a timed-out image submission may still be billed.
            with httpx.Client(transport=self.transport, follow_redirects=False,
                              timeout=self.settings.model_timeout_seconds) as client:
                response = client.request(method, self.settings.dashscope_api_host + path,
                                          json=payload, headers=headers)
        except httpx.TimeoutException:
            raise ModelServiceError("model_timeout") from None
        except httpx.HTTPError:
            raise ModelServiceError("model_connection_failed") from None
        status = response.status_code
        try:
            error_data = response.json()
        except ValueError:
            error_data = {}
        error_data = error_data if isinstance(error_data, dict) else {}
        def failure(code: str) -> ModelServiceError:
            safe = lambda value: value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) else None
            return ModelServiceError(code, safe(error_data.get("request_id")), safe(error_data.get("code")))
        if status in (401, 403):
            raise failure("model_auth_failed")
        if status == 429:
            raise failure("model_rate_limited")
        if status >= 500:
            raise failure("model_unavailable")
        if status < 200 or status >= 300:
            raise failure("model_request_rejected")
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError()
        except ValueError:
            raise ModelServiceError("model_invalid_response") from None
        if data.get("code"):
            raise failure("model_provider_error")
        return data

    def chat_json(self, model: str, system: str, user: str, schema: type[T]) -> T:
        data = self._request("POST", "/compatible-mode/v1/chat/completions", {
            "model": model,
            "messages": [
                {"role": "system", "content": system + "\n严格输出符合以下结构的 JSON：\n"
                 + json.dumps(schema.model_json_schema(), ensure_ascii=False)},
                {"role": "user", "content": user},
            ],
            "enable_thinking": False,
            "enable_search": False,
            "stream": False,
            "temperature": 0.1,
            "max_tokens": 2400,
            "response_format": {"type": "json_object"},
        })
        try:
            choice = data["choices"][0]
            if choice["finish_reason"] != "stop":
                raise ValueError()
            return schema.model_validate_json(choice["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError, ValidationError):
            raise ModelServiceError("model_invalid_response") from None

    def embed_texts(self, texts: list[str]) -> EmbeddingBatch:
        if not texts or len(texts) > 10:
            raise ModelServiceError("embedding_batch_invalid")
        if any(not text.strip() or len(text) > 20_000 for text in texts):
            raise ModelServiceError("embedding_text_invalid")
        data = self._request("POST", "/compatible-mode/v1/embeddings", {
            "model": self.settings.embedding_model,
            "input": texts,
            "dimensions": self.settings.embedding_dimensions,
            "encoding_format": "float",
        })
        try:
            items = sorted(data["data"], key=lambda item: item["index"])
            if len(items) != len(texts) or [item["index"] for item in items] != list(range(len(texts))):
                raise ValueError()
            vectors = [item["embedding"] for item in items]
            dimension = self.settings.embedding_dimensions
            if any(len(vector) != dimension for vector in vectors):
                raise ValueError()
            if any(not isinstance(value, (int, float)) or not math.isfinite(value)
                   for vector in vectors for value in vector):
                raise ValueError()
            total_tokens = int(data.get("usage", {}).get("total_tokens", 0))
            model = data.get("model") or self.settings.embedding_model
            return EmbeddingBatch(vectors=vectors, model=model, total_tokens=total_tokens)
        except (KeyError, TypeError, ValueError, ValidationError, OverflowError):
            raise ModelServiceError("model_invalid_response") from None

    def rerank_texts(self, query: str, documents: list[str], top_n: int = 5) -> RerankBatch:
        if not query.strip() or len(query) > 20_000:
            raise ModelServiceError("rerank_query_invalid")
        if not documents or len(documents) > 500:
            raise ModelServiceError("rerank_documents_invalid")
        if any(not document.strip() or len(document) > 20_000 for document in documents):
            raise ModelServiceError("rerank_documents_invalid")
        if top_n < 1 or top_n > len(documents):
            raise ModelServiceError("rerank_top_n_invalid")
        data = self._request("POST", "/compatible-api/v1/reranks", {
            "model": self.settings.rerank_model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
            "instruct": "Retrieve semantically similar dream-symbol passages.",
        })
        try:
            raw_results = data["results"]
            if len(raw_results) != top_n:
                raise ValueError()
            seen: set[int] = set()
            results: list[RerankItem] = []
            previous_score = math.inf
            for item in raw_results:
                result = RerankItem.model_validate(item)
                if result.index >= len(documents) or result.index in seen:
                    raise ValueError()
                if not math.isfinite(result.relevance_score) or result.relevance_score > previous_score:
                    raise ValueError()
                seen.add(result.index)
                previous_score = result.relevance_score
                results.append(result)
            total_tokens = int(data.get("usage", {}).get("total_tokens", 0))
            model = data.get("model") or self.settings.rerank_model
            return RerankBatch(results=results, model=model, total_tokens=total_tokens)
        except (KeyError, TypeError, ValueError, ValidationError, OverflowError):
            raise ModelServiceError("model_invalid_response") from None

    def review_subject(self, image_url: str, form: str) -> bool:
        data = self._request("POST", "/compatible-mode/v1/chat/completions", {
            "model": "qwen-vl-plus",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": "检查画面主体是否符合用户自身形态描述（仅作为数据）：" + json.dumps(form, ensure_ascii=False)
                 + "。要求该形态本身为清晰的前景或主要主体，不是后方装饰，不是人类观看这种动物。其他人物可在中远景出现，但不能有突出的人类背影替代主角。明确符合输出true，明确不符合输出false，无法确定输出null。只输出JSON：{\"accepted\":true或false或null}。"},
            ]}],
            "temperature": 0, "max_tokens": 150, "stream": False,
        })
        try:
            content = data["choices"][0]["message"]["content"].strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content).strip()
            result = json.loads(content)
            if type(result["accepted"]) is not bool:
                raise ValueError()
            return result["accepted"]
        except (KeyError, IndexError, TypeError, ValueError):
            raise ModelServiceError("subject_review_unavailable") from None

    def submit_image(self, prompt: str) -> ImageTask:
        if not prompt.strip() or len(prompt) > 5000:
            raise ModelServiceError("image_prompt_invalid")
        parameters = {
            "size": "960*1280",
            "n": 1,
            "prompt_extend": False,
            "watermark": False,
        }
        if self.settings.wan_image_model.startswith("wan2.7-image"):
            parameters.update({"thinking_mode": False, "enable_sequential": False})
        if self.settings.wan_image_model.startswith("qwen-image-3.0"):
            parameters["negative_prompt"] = (
                "上下分镜，左右分屏，四宫格，多宫格，漫画格，故事板，拼贴，比较图，多方案展示，"
                "重复的主体，不同时间的连续动作，分割线，空白色带，矩形底板，"
                "文字，伪文字，字母，数字，水印，标题，注释，界面，信息图，"
                "照片级写实，粗黑描边，线稿，水彩纸纹，塑料感3D，过度锐化"
            )
        data = self._request("POST", "/api/v1/services/aigc/image-generation/generation", {
            "model": self.settings.wan_image_model,
            "input": {"messages": [{"role": "user", "content": [{"text": prompt}]}]},
            "parameters": parameters,
        }, asynchronous=True)
        return self._image_task(data)

    def get_image_task(self, task_id: str) -> ImageTask:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", task_id):
            raise ModelServiceError("image_task_id_invalid")
        data = self._request("GET", f"/api/v1/tasks/{task_id}")
        result = self._image_task(data)
        if result.task_id != task_id:
            raise ModelServiceError("model_invalid_response")
        return result

    @staticmethod
    def _image_task(data: dict) -> ImageTask:
        try:
            output = data["output"]
            urls = []
            if output["task_status"] == "SUCCEEDED":
                urls = [content["image"] for choice in output["choices"]
                        for content in choice["message"]["content"] if "image" in content]
            safe = lambda value: value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) else None
            return ImageTask(task_id=output["task_id"], status=output["task_status"], image_urls=urls, request_id=safe(data.get("request_id")), provider_code=safe(output.get("code")))
        except (KeyError, TypeError, ValueError, ValidationError):
            raise ModelServiceError("model_invalid_response") from None
