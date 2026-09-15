"""Aliyun TextModerationPlus adapter. No automatic retries or raw-content logs."""
import json
from dataclasses import dataclass
from typing import Literal

from alibabacloud_green20220302.client import Client
from alibabacloud_green20220302.models import TextModerationPlusRequest
from alibabacloud_tea_openapi.models import Config
from alibabacloud_tea_util.models import RuntimeOptions

from app.core.config import Settings


class ModerationError(RuntimeError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ModerationDecision:
    risk_level: str
    request_id: str | None

    @property
    def allowed(self) -> bool:
        # Initial policy: do not auto-release any flagged content; no review queue yet.
        return self.risk_level == "none"


class TextModerator:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self._client = client

    def configuration(self) -> dict:
        def present(secret):
            return bool(secret and secret.get_secret_value().strip())
        return {
            "mode": self.settings.moderation_mode,
            "region": self.settings.moderation_region,
            "credentials_configured": present(self.settings.moderation_access_key_id) and present(self.settings.moderation_access_key_secret),
            "live_connection_verified": False,
            "input_service": "llm_query_moderation",
            "output_service": "llm_response_moderation",
        }

    def check(self, text: str, direction: Literal["input", "output"]) -> ModerationDecision:
        if self.settings.moderation_mode != "aliyun":
            raise ModerationError("moderation_not_enabled")
        if not self.configuration()["credentials_configured"] or not self.settings.moderation_region:
            raise ModerationError("moderation_not_configured")
        if direction not in ("input", "output") or not isinstance(text, str) or not text.strip():
            raise ModerationError("moderation_invalid_input")
        limit = 2000 if direction == "input" else 5000
        if len(text) > limit:
            # Never truncate unreviewed content or silently split away its context.
            raise ModerationError("moderation_text_too_long")
        try:
            if self._client is None:
                region = self.settings.moderation_region
                self._client = Client(Config(
                    access_key_id=self.settings.moderation_access_key_id.get_secret_value(),
                    access_key_secret=self.settings.moderation_access_key_secret.get_secret_value(),
                    security_token=self.settings.moderation_security_token.get_secret_value() if self.settings.moderation_security_token else None,
                    region_id=region,
                    endpoint=f"green-cip.{region}.aliyuncs.com",
                    protocol="https",
                ))
            timeout_ms = int(self.settings.moderation_timeout_seconds * 1000)
            response = self._client.text_moderation_plus_with_options(
                TextModerationPlusRequest(
                    service="llm_query_moderation" if direction == "input" else "llm_response_moderation",
                    service_parameters=json.dumps({"content": text}, ensure_ascii=False),
                ),
                RuntimeOptions(connect_timeout=timeout_ms, read_timeout=timeout_ms, autoretry=False, max_attempts=1),
            )
            if response.status_code != 200 or response.body is None:
                raise ModerationError("moderation_unavailable")
            payload = response.body.to_map()
            if payload.get("Code") != 200:
                raise ModerationError("moderation_unavailable")
            data = payload.get("Data")
            risk = data.get("RiskLevel") if isinstance(data, dict) else None
            if risk not in ("none", "low", "medium", "high"):
                raise ModerationError("moderation_invalid_response")
            request_id = payload.get("RequestId")
            return ModerationDecision(risk, request_id if isinstance(request_id, str) else None)
        except ModerationError:
            raise
        except Exception:
            # Provider exceptions may contain request content or credentials.
            raise ModerationError("moderation_unavailable") from None

    def require_allowed(self, text: str, direction: Literal["input", "output"]) -> None:
        if not self.check(text, direction).allowed:
            raise ModerationError("content_review_required")
