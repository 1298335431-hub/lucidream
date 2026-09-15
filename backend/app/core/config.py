from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", PROJECT_ROOT / "backend" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = Field("development", alias="DREAMCARD_ENV")
    auth_enabled: bool = Field(True, alias="DREAMCARD_AUTH_ENABLED")
    image_quota_total: int = Field(8, ge=1, le=1000, alias="DREAMCARD_IMAGE_QUOTA_TOTAL")

    @model_validator(mode="after")
    def enforce_auth(self):
        if not self.auth_enabled and self.environment != "test":
            raise ValueError("仅测试环境允许关闭登录验证")
        return self
    model_mode: Literal["mock", "aliyun"] = Field("mock", alias="DREAMCARD_MODEL_MODE")
    dashscope_api_key: str | None = Field(None, alias="DASHSCOPE_API_KEY", repr=False)
    dashscope_api_host: str = Field("https://dashscope.aliyuncs.com", alias="DASHSCOPE_API_HOST")
    model_timeout_seconds: float = Field(20, gt=0, le=60, alias="DREAMCARD_MODEL_TIMEOUT_SECONDS")
    image_wait_seconds: int = Field(600, ge=120, le=3600, alias="DREAMCARD_IMAGE_WAIT_SECONDS")
    image_worker_enabled: bool = Field(True, alias="DREAMCARD_IMAGE_WORKER_ENABLED")
    qwen_interpret_model: str = Field("qwen3.7-plus", alias="DREAMCARD_QWEN_INTERPRET_MODEL")
    wan_image_model: str = Field("qwen-image-3.0-pro", alias="DREAMCARD_WAN_IMAGE_MODEL")
    qwen_extract_model: str = Field(
        "qwen3.8-flash", alias="DREAMCARD_QWEN_EXTRACT_MODEL"
    )
    embedding_model: str = Field(
        "text-embedding-v4", alias="DREAMCARD_EMBEDDING_MODEL"
    )
    embedding_dimensions: int = Field(
        512, ge=64, le=2048, alias="DREAMCARD_EMBEDDING_DIMENSIONS"
    )
    rerank_model: str = Field(
        "qwen3-rerank", alias="DREAMCARD_RERANK_MODEL"
    )
    database_path: Path = Field(
        PROJECT_ROOT / "data" / "dreamcard.db",
        alias="DREAMCARD_DATABASE_PATH",
    )
    knowledge_index_path: Path = Field(
        PROJECT_ROOT / "data" / "knowledge" / "dream_sources.sqlite3",
        alias="DREAMCARD_KNOWLEDGE_INDEX_PATH",
    )
    original_knowledge_shadow_mode: Literal["disabled", "local"] = Field(
        "local", alias="DREAMCARD_ORIGINAL_KNOWLEDGE_SHADOW_MODE"
    )
    original_knowledge_cards_path: Path = Field(
        PROJECT_ROOT
        / "data"
        / "knowledge"
        / "自建知识库"
        / "processed"
        / "cards.jsonl",
        alias="DREAMCARD_ORIGINAL_KNOWLEDGE_CARDS_PATH",
    )
    cors_origins: str = Field(
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8443,http://127.0.0.1:8443",
        alias="DREAMCARD_CORS_ORIGINS",
    )
    max_dream_chars: int = Field(300, alias="DREAMCARD_MAX_DREAM_CHARS")
    moderation_mode: Literal["disabled", "aliyun"] = Field("disabled", alias="DREAMCARD_MODERATION_MODE")
    moderation_region: Literal["cn-beijing", "cn-shanghai", "cn-hangzhou", "cn-shenzhen", "cn-chengdu"] | None = Field(None, alias="DREAMCARD_MODERATION_REGION")
    moderation_access_key_id: SecretStr | None = Field(None, alias="ALIBABA_CLOUD_ACCESS_KEY_ID", repr=False)
    moderation_access_key_secret: SecretStr | None = Field(None, alias="ALIBABA_CLOUD_ACCESS_KEY_SECRET", repr=False)
    moderation_security_token: SecretStr | None = Field(None, alias="ALIBABA_CLOUD_SECURITY_TOKEN", repr=False)
    moderation_timeout_seconds: float = Field(5, gt=0, le=20, alias="DREAMCARD_MODERATION_TIMEOUT_SECONDS")

    @field_validator("dashscope_api_key")
    @classmethod
    def clean_key(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("dashscope_api_host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        url = urlsplit(value)
        if (url.scheme != "https" or not url.hostname
                or not url.hostname.endswith(".aliyuncs.com")
                or url.username or url.password or url.port not in (None, 443)
                or url.path not in ("", "/") or url.query or url.fragment):
            raise ValueError("API Host 必须为阿里云 HTTPS 根地址")
        return value.rstrip("/")

    def parsed_cors_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]
