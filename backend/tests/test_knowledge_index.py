import json
from pathlib import Path

import pytest

from app.services.knowledge_index import KnowledgeIndex, load_chunks


def write_chunks(path: Path) -> None:
    records = [
        {
            "source_id": "book:one", "book": "Book", "author": "Author",
            "translator": None, "chapter": "Forest", "language": "en",
            "original_text": "A deer crossed the forest.",
            "source_line_start": 1, "source_line_end": 2,
            "source_file_sha256": "a" * 64, "source_url": "https://example.com",
            "rights_status": "candidate", "verified": False,
            "retrieval_enabled": True, "quality_flags": [],
        },
        {
            "source_id": "book:disabled", "book": "Book", "author": "Author",
            "translator": None, "chapter": "Other", "language": "en",
            "original_text": "See forest.", "source_line_start": 3,
            "source_line_end": 3, "source_file_sha256": "a" * 64,
            "source_url": "https://example.com", "rights_status": "candidate",
            "verified": False, "retrieval_enabled": False, "quality_flags": [],
        },
    ]
    path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")


def test_index_filters_resumes_and_searches(tmp_path):
    chunk_path = tmp_path / "chunks.jsonl"
    write_chunks(chunk_path)
    chunks = load_chunks([chunk_path])
    assert [chunk.source_id for chunk in chunks] == ["book:one"]

    index_path = tmp_path / "index.sqlite3"
    with KnowledgeIndex(index_path, "embedding-test", 3) as index:
        assert index.missing_chunks(chunks) == chunks
        index.add_batch(chunks, [[1.0, 0.0, 0.0]], 12)
        assert index.count() == 1
        assert index.total_tokens() == 12
        assert index.missing_chunks(chunks) == []
        result = index.search([1.0, 0.0, 0.0], limit=1)[0]
        assert result["source_id"] == "book:one"
        assert result["score"] == 1.0


def test_index_rejects_incompatible_configuration(tmp_path):
    path = tmp_path / "index.sqlite3"
    with KnowledgeIndex(path, "model-a", 3):
        pass
    with pytest.raises(ValueError, match="metadata mismatch"):
        KnowledgeIndex(path, "model-b", 3)


def test_index_rejects_changed_source(tmp_path):
    chunk_path = tmp_path / "chunks.jsonl"
    write_chunks(chunk_path)
    chunks = load_chunks([chunk_path])
    with KnowledgeIndex(tmp_path / "index.sqlite3", "model", 3) as index:
        index.add_batch(chunks, [[1.0, 0.0, 0.0]], 1)
        changed = type(chunks[0])(**{
            **chunks[0].__dict__, "original_text": "Changed text"
        })
        with pytest.raises(ValueError, match="indexed source changed"):
            index.missing_chunks([changed])


def test_hybrid_search_keeps_exact_heading_candidate(tmp_path):
    chunk_path = tmp_path / "chunks.jsonl"
    records = []
    for index, chapter in enumerate(("Raccoon", "Deer", "Forest")):
        records.append({
            "source_id": f"book:{index}", "book": "Book", "author": "Author",
            "translator": None, "chapter": chapter, "language": "en",
            "original_text": f"A passage about {chapter}.", "source_line_start": index + 1,
            "source_line_end": index + 1, "source_file_sha256": "a" * 64,
            "source_url": "https://example.com", "rights_status": "candidate",
            "verified": False, "retrieval_enabled": True, "quality_flags": [],
        })
    chunk_path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
    chunks = load_chunks([chunk_path])
    with KnowledgeIndex(tmp_path / "index.sqlite3", "model", 3) as index:
        # Vector-only similarity incorrectly favors Raccoon; lexical recall must retain Deer.
        index.add_batch(chunks, [[1, 0, 0], [0, 1, 0], [0, 0, 1]], 3)
        results = index.hybrid_candidates([[1, 0, 0]], ["deer"], limit=2)
        assert {item["chapter"] for item in results} == {"Raccoon", "Deer"}
