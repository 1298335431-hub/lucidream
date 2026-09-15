"""Local-only retrieval for reviewed, original Simplified Chinese dream cards."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^0-9a-z\u3400-\u9fff]+", re.IGNORECASE)

# One-character Chinese terms are normally too ambiguous for substring matching
# (for example, 水 in 水果 and 海 in 海外).  These are the small, reviewed set of
# concrete dream symbols that may be passed from the *confirmed* character/object
# fields only.  They are never enabled for free-text clarification answers.
_CONFIRMED_SINGLE_CHARACTER_SYMBOLS = frozenset(
    {
        "蛇",
        "猫",
        "狗",
        "鱼",
        "鸟",
        "马",
        "鹿",
        "虎",
        "狼",
        "兔",
        "龙",
        "牛",
        "羊",
        "门",
        "桥",
        "车",
        "船",
        "火",
        "水",
        "山",
        "海",
        "雨",
        "雪",
        "血",
    }
)


def normalize_text(value: str) -> str:
    """Normalize a Chinese query without external tokenization dependencies."""
    return _PUNCT_RE.sub("", _SPACE_RE.sub("", value).casefold())


@dataclass(frozen=True)
class OriginalKnowledgeCard:
    card_id: str
    title: str
    aliases: tuple[str, ...]
    retrieval_terms: tuple[str, ...]
    category: str
    scope_note: str
    original_interpretation: str
    reflection_prompts: tuple[str, ...]
    gentle_actions: tuple[str, ...]
    safety_note: str
    rights_status: str
    status: str
    source_file: str
    primary_terms: tuple[str, ...] = ()
    supporting_card_ids: tuple[str, ...] = ()

    @classmethod
    def from_record(cls, record: dict) -> "OriginalKnowledgeCard":
        return cls(
            card_id=record["card_id"],
            title=record["title"],
            aliases=tuple(record.get("aliases", [])),
            primary_terms=tuple(record.get("primary_terms", [])),
            supporting_card_ids=tuple(record.get("supporting_card_ids", [])),
            retrieval_terms=tuple(record.get("retrieval_terms", [])),
            category=record["category"],
            scope_note=record["scope_note"],
            original_interpretation=record["original_interpretation"],
            reflection_prompts=tuple(record.get("reflection_prompts", [])),
            gentle_actions=tuple(record.get("gentle_actions", [])),
            safety_note=record["safety_note"],
            rights_status=record["rights_status"],
            status=record["status"],
            source_file=record["source_file"],
        )


@dataclass(frozen=True)
class LocalRetrievalHit:
    card: OriginalKnowledgeCard
    score: float
    matched_terms: tuple[str, ...]
    role: str = "primary"


@dataclass(frozen=True)
class LocalRetrievalResult:
    hits: tuple[LocalRetrievalHit, ...]
    fallback: bool


class LocalOriginalKnowledgeRetriever:
    """Deterministic title/alias/term retrieval that never calls a cloud model."""

    def __init__(self, cards: Iterable[OriginalKnowledgeCard], min_score: float = 3.0):
        self.cards = tuple(cards)
        self.min_score = min_score

    @classmethod
    def from_jsonl(
        cls, path: Path, min_score: float = 3.0
    ) -> "LocalOriginalKnowledgeRetriever":
        cards: list[OriginalKnowledgeCard] = []
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid_jsonl_line:{line_number}") from exc
                cards.append(OriginalKnowledgeCard.from_record(record))
        if not cards:
            raise ValueError("original_knowledge_cards_empty")
        return cls(cards, min_score=min_score)

    def retrieve(
        self,
        query: str,
        limit: int = 3,
        confirmed_single_character_terms: Iterable[str] = (),
    ) -> LocalRetrievalResult:
        """Retrieve cards from a privacy-preserving confirmed-symbol query.

        Single-character terms remain disabled by default.  A small reviewed
        allowlist can be enabled only when a term was explicitly confirmed as a
        character or object in the product flow.
        """
        if limit < 1:
            raise ValueError("local_retrieval_limit_invalid")
        normalized_query = normalize_text(query)
        if not normalized_query:
            return LocalRetrievalResult(hits=(), fallback=True)
        allowed_single_character_terms = {
            normalized
            for value in confirmed_single_character_terms
            if (normalized := normalize_text(value)) in _CONFIRMED_SINGLE_CHARACTER_SYMBOLS
        }

        scored: list[LocalRetrievalHit] = []
        for card in self.cards:
            score, matched = self._score_card(
                normalized_query, card, allowed_single_character_terms
            )
            if score >= self.min_score:
                scored.append(
                    LocalRetrievalHit(card=card, score=score, matched_terms=tuple(matched))
                )
        scored.sort(key=lambda hit: (-hit.score, hit.card.card_id))
        hits = self._select_primary_and_supporting(scored, limit=limit)
        return LocalRetrievalResult(hits=hits, fallback=not hits)

    def _select_primary_and_supporting(
        self, scored: list[LocalRetrievalHit], *, limit: int
    ) -> tuple[LocalRetrievalHit, ...]:
        """Keep one dominant scene and only materially relevant supporting cards.

        The local selector is deliberately deterministic.  It never asks a model
        to choose a card, so the decision remains inspectable and stable for
        evaluation.  A supporting card must carry at least 60 percent of the
        primary card's score.  This filters incidental one-word matches while
        retaining a second scene when it has meaningful evidence.
        """
        if not scored:
            return ()

        primary = scored[0]
        primary_hit = LocalRetrievalHit(
            card=primary.card,
            score=primary.score,
            matched_terms=primary.matched_terms,
            role="primary",
        )
        allowed_supporting_ids = set(primary.card.supporting_card_ids)
        minimum_support_score = max(
            self.min_score,
            primary.score * (0.45 if allowed_supporting_ids else 0.6),
        )
        supporting = [
            LocalRetrievalHit(
                card=hit.card,
                score=hit.score,
                matched_terms=hit.matched_terms,
                role="supporting",
            )
            for hit in scored[1:]
            if hit.score > minimum_support_score
            and (
                not allowed_supporting_ids
                or hit.card.card_id in allowed_supporting_ids
            )
        ]
        # One main scene plus no more than two genuinely supported details.
        return tuple([primary_hit, *supporting[: max(0, min(limit - 1, 2))]])

    @staticmethod
    def _score_card(
        normalized_query: str,
        card: OriginalKnowledgeCard,
        allowed_single_character_terms: set[str],
    ) -> tuple[float, list[str]]:
        # Primary terms are deliberately authored only for cards whose scene
        # needs to outrank an otherwise strong local action.  Cards without
        # this metadata retain the conservative legacy weighting.  Related
        # primary terms are alternatives, not independent evidence, so a card
        # receives only its strongest primary-term score.
        candidates: list[tuple[str, float]] = [(card.title, 8.0)]
        candidates.extend((value, 6.0) for value in card.aliases)
        candidates.extend((value, 3.0) for value in card.retrieval_terms)

        matched: list[str] = []
        score = 0.0
        seen: set[str] = set()
        primary_scores: list[float] = []
        for raw_term in card.primary_terms:
            term = normalize_text(raw_term)
            if (len(term) < 2 and term not in allowed_single_character_terms) or term in seen:
                continue
            seen.add(term)
            if term in normalized_query:
                matched.append(raw_term)
                primary_scores.append(12.0 + min(len(term), 6) * 0.25)
        if primary_scores:
            score += max(primary_scores)

        for raw_term, weight in candidates:
            term = normalize_text(raw_term)
            # A single Han character creates obvious false positives, such as
            # matching 水 in 水果 or 海 in 海外.  Only a reviewed term that came
            # from confirmed character/object fields may bypass this safeguard.
            if (len(term) < 2 and term not in allowed_single_character_terms) or term in seen:
                continue
            seen.add(term)
            if term in normalized_query:
                matched.append(raw_term)
                # An explicitly confirmed concrete symbol such as 狼 or 蛇 is
                # stronger evidence than a generic multi-character action such
                # as 跟着我.  It stays disabled unless confirmed upstream.
                effective_weight = max(weight, 6.0) if len(term) == 1 else weight
                score += effective_weight + min(len(term), 6) * 0.25
        return score, matched
