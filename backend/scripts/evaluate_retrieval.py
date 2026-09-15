"""Paid live evaluation for the controlled retrieval path; no interpretation call."""

from __future__ import annotations

import json

from app.core.config import Settings
from app.schemas.dream import DreamSymbols
from app.services.aliyun import ModelServiceError
from app.services.retrieval import DreamRetrievalService


CASES = (
    ("月光下的森林和鹿", DreamSymbols(
        scenes=["月光下的森林"], characters=["鹿"], objects=["月亮"], emotions=["平静"],
    )),
    ("从高处坠落", DreamSymbols(
        scenes=["高处"], actions=["坠落"], emotions=["害怕"],
    )),
    ("在水中行走", DreamSymbols(
        scenes=["水中"], objects=["水"], actions=["行走"],
    )),
    ("回到以前住过的旧房子", DreamSymbols(
        scenes=["以前住过的旧房子"], actions=["回到"], relationships=["童年的家"],
    )),
    ("被陌生人追赶", DreamSymbols(
        characters=["陌生人"], actions=["被追赶", "奔跑"], emotions=["害怕"],
        relationships=["陌生人追赶我"],
    )),
)


def main() -> None:
    settings = Settings()
    if settings.model_mode != "aliyun":
        raise SystemExit("DREAMCARD_MODEL_MODE must be aliyun")
    service = DreamRetrievalService(settings)
    totals = {"embedding_tokens": 0, "rerank_tokens": 0}
    try:
        for label, symbols in CASES:
            result = service.retrieve(symbols, candidate_limit=20, final_limit=5)
            totals["embedding_tokens"] += result.embedding_tokens
            totals["rerank_tokens"] += result.rerank_tokens
            print(json.dumps({
                "case": label,
                "english_queries": result.expansion.english_queries,
                "english_keywords": result.expansion.english_keywords,
                "results": [{
                    "book": passage.book,
                    "chapter": passage.chapter,
                    "source_id": passage.source_id,
                    "rerank_score": passage.rerank_score,
                    "excerpt": passage.original_text[:180],
                } for passage in result.passages],
                "embedding_tokens": result.embedding_tokens,
                "rerank_tokens": result.rerank_tokens,
            }, ensure_ascii=False), flush=True)
    except ModelServiceError as exc:
        raise SystemExit(f"provider_error:{exc.code}") from None
    print(json.dumps({"totals": totals}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
