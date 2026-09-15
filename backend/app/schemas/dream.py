from typing import Literal

import re
from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator, computed_field


DreamStatus = Literal[
    "draft",
    "reviewing_symbols",
    "awaiting_clarification",
    "ready_to_generate",
    "failed",
    "safety_interrupted",
]


class DreamSymbols(BaseModel):
    dreamer: list[str] = Field(default_factory=list, description="当前梦中的我，原文明确的自身形态；不包含其他角色")
    scenes: list[str] = Field(default_factory=list)
    characters: list[str] = Field(default_factory=list)
    objects: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    emotions: list[str] = Field(default_factory=list)
    relationships: list[str] = Field(default_factory=list)
    reality_context: list[str] = Field(default_factory=list)
    uncertain_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def separate_dreamer(self):
        # Preserve possessives and independently appearing future selves.
        others = []
        for item in self.characters:
            if item in {"我", "自己", "我自己", "梦中的我", "做梦者"} or re.search(r"[（(](?:我|自己|梦中的我)[）)]$", item):
                if item not in self.dreamer:
                    self.dreamer.append(item)
            else:
                others.append(item)
        self.characters = others
        unique = {}
        for item in self.dreamer:
            form = re.sub(r"[（(](?:我|自己|梦中的我)[）)]$", "", item).strip()
            form = re.sub(r"^(?:我梦见)?(?:梦中的我|我自己|自己|我)?(?:在梦中|在梦里)?(?:变成了?|是)?", "", form)
            form = re.sub(r"^一[只个位条头]", "", form).strip()
            if form and form not in {"做梦者", "人", "人物"}:
                unique.setdefault(form.replace("的", ""), form)
        self.dreamer = list(unique.values())[:20]
        return self

    @field_validator("*", mode="before")
    @classmethod
    def normalize_lists(cls, value: object) -> object:
        if value is None:
            return []
        return value

    @field_validator("*", mode="after")
    @classmethod
    def clean_items(cls, value: list[str], info: ValidationInfo) -> list[str]:
        cleaned: list[str] = []
        item_limit = 180 if info.field_name == "reality_context" else 80
        for item in value:
            normalized = " ".join(item.strip().split())
            if normalized and normalized not in cleaned:
                cleaned.append(normalized[:item_limit])
        return cleaned[:20]


class ClarificationQuestion(BaseModel):
    question: str = Field(min_length=1, max_length=200)
    options: list[str] = Field(min_length=2, max_length=5)


class ExtractionResult(BaseModel):
    symbols: DreamSymbols
    clarification: ClarificationQuestion | None = None


class ExtractDreamRequest(BaseModel):
    dream_text: str = Field(min_length=1)

    @field_validator("dream_text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("梦境内容不能为空")
        return normalized


class UpdateSymbolsRequest(BaseModel):
    symbols: DreamSymbols
    character_appearance: Literal["unspecified", "male", "female", "none", "other"] | None = None
    character_form: str = Field(default="", max_length=100)
    clarification_answer: str | None = Field(default=None, max_length=100)


class DreamSessionResponse(BaseModel):
    id: str
    character_appearance: Literal["unspecified", "male", "female", "none", "other"] = "unspecified"
    character_form: str = ""
    dream_text: str
    status: DreamStatus
    symbols: DreamSymbols
    clarification: ClarificationQuestion | None = None
    clarification_answer: str | None = None
    safety_message: str | None = None
    revision: int
    created_at: str
    updated_at: str
    model_mode: str

    @computed_field
    @property
    def dreamer_suggestion(self) -> dict[str, str] | None:
        if len(self.symbols.dreamer) != 1:
            return None
        form = self.symbols.dreamer[0]
        if re.search(r"不确定|可能|记不清|或|变成|然后", form):
            return None
        if form in {"没有明确形象", "没有形象", "第一人称视角"}:
            return {"appearance": "unspecified", "form": ""}
        if re.fullmatch(r"(?:一名|一个)?(?:男生|男性|男孩|男人)(?:形象)?", form):
            return {"appearance": "male", "form": ""}
        if re.fullmatch(r"(?:一名|一个)?(?:女生|女性|女孩|女人)(?:形象)?", form):
            return {"appearance": "female", "form": ""}
        return {"appearance": "other", "form": form[:100]}


class DeleteResponse(BaseModel):
    deleted: bool


class DreamImageResponse(BaseModel):
    variants: list[str] = Field(default_factory=list)
    selected_variant: str | None = None
    session_id: str
    revision: int = Field(ge=1)
    status: Literal["pending", "processing", "completed", "failed"]
    image_url: str | None = None
    retry_after_seconds: int | None = Field(default=None, ge=1, le=30)
    recovery_action: Literal['retry_generation', 'retry_review', 'check_task', 'contact_support'] | None = None
    supplementary_attempts: int = Field(default=0, ge=0)
    failure_reason: Literal["contains_text", "contains_band", "contains_panels", "generation_failed", "subject_mismatch", "subject_review_unavailable", "image_review_unavailable", "generation_timeout", "submission_unknown", "prompt_too_long"] | None = None
