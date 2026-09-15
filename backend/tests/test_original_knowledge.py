import json
from pathlib import Path

from app.services.original_knowledge import (
    LocalOriginalKnowledgeRetriever,
    OriginalKnowledgeCard,
    normalize_text,
)


def make_card(
    card_id: str,
    title: str,
    terms: list[str],
    *,
    primary_terms: list[str] | None = None,
    supporting_card_ids: list[str] | None = None,
) -> OriginalKnowledgeCard:
    return OriginalKnowledgeCard(
        card_id=card_id,
        title=title,
        aliases=(),
        primary_terms=tuple(primary_terms or []),
        supporting_card_ids=tuple(supporting_card_ids or []),
        retrieval_terms=tuple(terms),
        category="test",
        scope_note="scope",
        original_interpretation="interpretation",
        reflection_prompts=(),
        gentle_actions=(),
        safety_note="safe",
        rights_status="original_pending_review",
        status="draft",
        source_file="test.md",
    )


def test_normalize_text_keeps_chinese_and_ascii() -> None:
    assert normalize_text(" 牙齿，ABC！ ") == "牙齿abc"


def test_retriever_returns_multiple_cards_and_fallback() -> None:
    retriever = LocalOriginalKnowledgeRetriever(
        [
            make_card("DREAM-001", "被追赶", ["被人追", "逃跑"]),
            make_card("DREAM-015", "水域", ["洪水", "海边"]),
        ]
    )
    result = retriever.retrieve("我被人追到海边")
    assert [hit.card.card_id for hit in result.hits] == ["DREAM-001", "DREAM-015"]
    assert result.fallback is False
    assert retriever.retrieve("在月球商店买东西").fallback is True


def test_retriever_keeps_primary_and_filters_low_signal_supporting_card() -> None:
    retriever = LocalOriginalKnowledgeRetriever(
        [
            make_card(
                "DREAM-074", "搬家离开与旅行准备", ["搬家", "收拾行李", "出发"],
                primary_terms=["搬家", "准备旅行"], supporting_card_ids=["DREAM-059"],
            ),
            make_card(
                "DREAM-059", "衣服鞋子与行李", ["收拾行李", "行李"],
                primary_terms=["行李", "收拾行李"],
            ),
            make_card("DREAM-005", "迟到与赶不上", ["赶不上"]),
        ]
    )

    result = retriever.retrieve("我在搬家时收拾行李准备出发，却总是赶不上")

    assert [hit.card.card_id for hit in result.hits] == ["DREAM-074", "DREAM-059"]
    assert [hit.role for hit in result.hits] == ["primary", "supporting"]


def test_retriever_promotes_confirmed_single_character_wolf_over_generic_following() -> None:
    retriever = LocalOriginalKnowledgeRetriever(
        [
            make_card("DREAM-069", "鬼怪怪物与非人追随者", ["跟着我"]),
            make_card("DREAM-071", "马狼与大型动物", ["狼"]),
        ]
    )

    result = retriever.retrieve("一只狼一直跟着我", confirmed_single_character_terms=["狼"])

    assert result.hits[0].card.card_id == "DREAM-071"
    assert result.hits[0].role == "primary"
    assert len(result.hits) == 1


def test_retriever_promotes_pet_injury_over_generic_injury_card() -> None:
    retriever = LocalOriginalKnowledgeRetriever(
        [
            make_card("DREAM-066", "血受伤与疼痛", ["受伤了", "受伤"]),
            make_card(
                "DREAM-072", "宠物走失与动物受伤", ["猫受伤", "动物受伤"],
                primary_terms=["猫受伤", "动物受伤"], supporting_card_ids=["DREAM-030"],
            ),
            make_card("DREAM-030", "猫狗与宠物", ["猫"]),
        ]
    )

    result = retriever.retrieve(
        "猫走丢后我找到它，发现猫受伤了",
        confirmed_single_character_terms=["猫"],
    )

    assert [hit.card.card_id for hit in result.hits] == ["DREAM-072", "DREAM-030"]
    assert [hit.role for hit in result.hits] == ["primary", "supporting"]


def test_retriever_ignores_single_character_false_positives() -> None:
    retriever = LocalOriginalKnowledgeRetriever(
        [make_card("DREAM-015", "水域", ["水", "海", "洪水", "海边"])]
    )
    assert retriever.retrieve("我在海外的水果店买东西").fallback is True
    assert retriever.retrieve("洪水淹没了街道").fallback is False


def test_retriever_allows_reviewed_single_character_only_when_confirmed() -> None:
    retriever = LocalOriginalKnowledgeRetriever(
        [make_card("DREAM-029", "蛇", ["蛇", "很多蛇"])]
    )

    assert retriever.retrieve("蛇").fallback is True
    result = retriever.retrieve("蛇", confirmed_single_character_terms=["蛇"])
    assert result.fallback is False
    assert result.hits[0].card.card_id == "DREAM-029"
    assert result.hits[0].matched_terms == ("蛇",)

    # Terms outside the reviewed allowlist cannot bypass the default safeguard.
    assert retriever.retrieve("人", confirmed_single_character_terms=["人"]).fallback is True


def test_from_jsonl_rejects_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "cards.jsonl"
    path.write_text("", encoding="utf-8")
    try:
        LocalOriginalKnowledgeRetriever.from_jsonl(path)
    except ValueError as exc:
        assert str(exc) == "original_knowledge_cards_empty"
    else:
        raise AssertionError("empty original knowledge must fail")


def test_from_jsonl_loads_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "cards.jsonl"
    record = {
        "card_id": "DREAM-001",
        "title": "被追赶",
        "aliases": ["逃跑"],
        "retrieval_terms": ["追"],
        "category": "动作",
        "scope_note": "scope",
        "original_interpretation": "text",
        "reflection_prompts": [],
        "gentle_actions": [],
        "safety_note": "safe",
        "rights_status": "original_pending_review",
        "status": "draft",
        "source_file": "DREAM-001.md",
    }
    path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")
    retriever = LocalOriginalKnowledgeRetriever.from_jsonl(path)
    assert retriever.cards[0].title == "被追赶"


def test_reviewed_cards_prioritize_previously_deceased_relative() -> None:
    project_root = Path(__file__).resolve().parents[2]
    retriever = LocalOriginalKnowledgeRetriever.from_jsonl(
        project_root
        / "data"
        / "knowledge"
        / "自建知识库"
        / "processed"
        / "cards.jsonl"
    )

    result = retriever.retrieve(
        "小时候住过的旧房子 已经去世的外婆 窗边 织毛衣 房间越来越远 外婆已经去世"
    )

    assert result.hits[0].card.card_id == "DREAM-023"
    assert "已经去世的" in result.hits[0].matched_terms
    assert any(hit.card.card_id == "DREAM-012" for hit in result.hits[1:])
