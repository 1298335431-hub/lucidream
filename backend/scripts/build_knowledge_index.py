"""Build or evaluate the local dream-book embedding index.

Provider POST calls are intentionally sequential and have no automatic retry.
Every successful batch is committed, so an interrupted run can be resumed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.core.config import Settings
from app.services.aliyun import AliyunModels, ModelServiceError
from app.services.knowledge_index import KnowledgeIndex, load_chunks


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MATERIAL_ROOT = PROJECT_ROOT / "data" / "knowledge" / "解梦素材"
CHUNK_PATHS = (
    MATERIAL_ROOT / "freud-interpretation-of-dreams-en" / "processed" / "chunks.jsonl",
    MATERIAL_ROOT / "miller-ten-thousand-dreams-en" / "processed" / "chunks.jsonl",
)
DEFAULT_QUERIES = (
    "梦见月光下的森林和一只鹿",
    "梦见自己从高处坠落",
    "梦见自己在水中行走",
    "梦见回到以前住过的旧房子",
    "梦见被一个陌生人追赶",
)


def batches(items: list, size: int):
    for start in range(0, len(items), size):
        yield items[start:start + size]


def build(settings: Settings) -> None:
    chunks = load_chunks(CHUNK_PATHS)
    model = AliyunModels(settings)
    with KnowledgeIndex(settings.knowledge_index_path, settings.embedding_model,
                        settings.embedding_dimensions) as index:
        missing = index.missing_chunks(chunks)
        print(json.dumps({
            "event": "start", "total": len(chunks), "existing": index.count(),
            "missing": len(missing), "model": settings.embedding_model,
            "dimensions": settings.embedding_dimensions,
        }, ensure_ascii=False), flush=True)
        completed = 0
        for batch in batches(missing, 10):
            result = model.embed_texts([chunk.embedding_text for chunk in batch])
            if result.model != settings.embedding_model:
                raise ValueError("provider returned an unexpected embedding model")
            index.add_batch(batch, result.vectors, result.total_tokens)
            completed += len(batch)
            if completed % 100 == 0 or completed == len(missing):
                print(json.dumps({
                    "event": "progress", "completed_this_run": completed,
                    "indexed": index.count(), "total_tokens": index.total_tokens(),
                }, ensure_ascii=False), flush=True)
        print(json.dumps({
            "event": "complete", "indexed": index.count(),
            "total_tokens": index.total_tokens(),
        }, ensure_ascii=False), flush=True)


def evaluate(settings: Settings, queries: tuple[str, ...]) -> None:
    model = AliyunModels(settings)
    result = model.embed_texts(list(queries))
    with KnowledgeIndex(settings.knowledge_index_path, settings.embedding_model,
                        settings.embedding_dimensions) as index:
        if index.count() == 0:
            raise ValueError("knowledge index is empty")
        for query, vector in zip(queries, result.vectors, strict=True):
            print(json.dumps({
                "query": query,
                "results": index.search(vector, limit=3),
            }, ensure_ascii=False), flush=True)
    print(json.dumps({"evaluation_tokens": result.total_tokens}, ensure_ascii=False), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("build", "evaluate"))
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()
    settings = Settings()
    if settings.model_mode != "aliyun":
        raise SystemExit("DREAMCARD_MODEL_MODE must be aliyun")
    try:
        if args.command == "build":
            build(settings)
        else:
            evaluate(settings, tuple(args.queries or DEFAULT_QUERIES))
    except ModelServiceError as exc:
        raise SystemExit(f"provider_error:{exc.code}") from None


if __name__ == "__main__":
    main()
