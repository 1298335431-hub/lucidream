"""Local, traceable vector index for the approved dream-book candidates."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


SCHEMA_VERSION = "1"


@dataclass(frozen=True)
class KnowledgeChunk:
    source_id: str
    book: str
    author: str
    translator: str | None
    chapter: str
    language: str
    original_text: str
    source_line_start: int
    source_line_end: int
    source_file_sha256: str
    source_url: str
    rights_status: str
    verified: bool
    quality_flags: tuple[str, ...]

    @property
    def embedding_text(self) -> str:
        return f"{self.chapter}\n\n{self.original_text}"

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.embedding_text.encode("utf-8")).hexdigest()


def load_chunks(paths: Iterable[Path]) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    seen: set[str] = set()
    for path in paths:
        with path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                data = json.loads(line)
                if not data.get("retrieval_enabled", False):
                    continue
                source_id = str(data["source_id"])
                if source_id in seen:
                    raise ValueError(f"duplicate source_id: {source_id}")
                seen.add(source_id)
                chunks.append(KnowledgeChunk(
                    source_id=source_id,
                    book=str(data["book"]),
                    author=str(data["author"]),
                    translator=data.get("translator"),
                    chapter=str(data["chapter"]),
                    language=str(data["language"]),
                    original_text=str(data["original_text"]),
                    source_line_start=int(data["source_line_start"]),
                    source_line_end=int(data["source_line_end"]),
                    source_file_sha256=str(data["source_file_sha256"]),
                    source_url=str(data["source_url"]),
                    rights_status=str(data["rights_status"]),
                    verified=bool(data["verified"]),
                    quality_flags=tuple(data.get("quality_flags", [])),
                ))
    return chunks


def encode_vector(vector: list[float], dimensions: int) -> tuple[bytes, float]:
    if len(vector) != dimensions or any(not math.isfinite(value) for value in vector):
        raise ValueError("invalid embedding vector")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        raise ValueError("zero embedding vector")
    return array("f", vector).tobytes(), norm


def decode_vector(blob: bytes, dimensions: int) -> array:
    vector = array("f")
    vector.frombytes(blob)
    if len(vector) != dimensions:
        raise ValueError("stored embedding dimension mismatch")
    return vector


class KnowledgeIndex:
    def __init__(self, path: Path, model: str, dimensions: int):
        self.path = path
        self.model = model
        self.dimensions = dimensions
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self._create_schema()
        self._validate_metadata()

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "KnowledgeIndex":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def _create_schema(self) -> None:
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=NORMAL;
            CREATE TABLE IF NOT EXISTS index_metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                source_id TEXT PRIMARY KEY,
                book TEXT NOT NULL,
                author TEXT NOT NULL,
                translator TEXT,
                chapter TEXT NOT NULL,
                language TEXT NOT NULL,
                original_text TEXT NOT NULL,
                source_line_start INTEGER NOT NULL,
                source_line_end INTEGER NOT NULL,
                source_file_sha256 TEXT NOT NULL,
                source_url TEXT NOT NULL,
                rights_status TEXT NOT NULL,
                verified INTEGER NOT NULL CHECK (verified IN (0, 1)),
                quality_flags TEXT NOT NULL,
                content_sha256 TEXT NOT NULL,
                embedding_model TEXT NOT NULL,
                embedding_dimensions INTEGER NOT NULL,
                embedding BLOB NOT NULL,
                embedding_norm REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS chunks_book_idx ON chunks(book);
        """)
        self.connection.commit()

    def _validate_metadata(self) -> None:
        existing = dict(self.connection.execute(
            "SELECT key, value FROM index_metadata"
        ).fetchall())
        expected = {
            "schema_version": SCHEMA_VERSION,
            "embedding_model": self.model,
            "embedding_dimensions": str(self.dimensions),
        }
        if existing:
            for key, value in expected.items():
                if existing.get(key) != value:
                    raise ValueError(f"knowledge index metadata mismatch: {key}")
        else:
            self.connection.executemany(
                "INSERT INTO index_metadata(key, value) VALUES (?, ?)",
                expected.items(),
            )
            self.connection.execute(
                "INSERT INTO index_metadata(key, value) VALUES ('total_tokens', '0')"
            )
            self.connection.commit()

    def missing_chunks(self, chunks: Iterable[KnowledgeChunk]) -> list[KnowledgeChunk]:
        stored = {
            row["source_id"]: row["content_sha256"]
            for row in self.connection.execute(
                "SELECT source_id, content_sha256 FROM chunks"
            )
        }
        missing: list[KnowledgeChunk] = []
        for chunk in chunks:
            existing_hash = stored.get(chunk.source_id)
            if existing_hash is None:
                missing.append(chunk)
            elif existing_hash != chunk.content_sha256:
                raise ValueError(f"indexed source changed: {chunk.source_id}")
        return missing

    def add_batch(self, chunks: list[KnowledgeChunk], vectors: list[list[float]],
                  total_tokens: int) -> None:
        if len(chunks) != len(vectors):
            raise ValueError("chunk/vector count mismatch")
        rows = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            blob, norm = encode_vector(vector, self.dimensions)
            rows.append((
                chunk.source_id, chunk.book, chunk.author, chunk.translator,
                chunk.chapter, chunk.language, chunk.original_text,
                chunk.source_line_start, chunk.source_line_end,
                chunk.source_file_sha256, chunk.source_url, chunk.rights_status,
                int(chunk.verified), json.dumps(chunk.quality_flags),
                chunk.content_sha256, self.model, self.dimensions, blob, norm,
            ))
        with self.connection:
            self.connection.executemany("""
                INSERT INTO chunks (
                    source_id, book, author, translator, chapter, language,
                    original_text, source_line_start, source_line_end,
                    source_file_sha256, source_url, rights_status, verified,
                    quality_flags, content_sha256, embedding_model,
                    embedding_dimensions, embedding, embedding_norm
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, rows)
            self.connection.execute("""
                UPDATE index_metadata
                SET value = CAST(CAST(value AS INTEGER) + ? AS TEXT)
                WHERE key = 'total_tokens'
            """, (total_tokens,))

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])

    def total_tokens(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM index_metadata WHERE key = 'total_tokens'"
        ).fetchone()
        return int(row[0])

    def search(self, query_vector: list[float], limit: int = 5) -> list[dict]:
        _, query_norm = encode_vector(query_vector, self.dimensions)
        results: list[tuple[float, sqlite3.Row]] = []
        for row in self.connection.execute("""
            SELECT source_id, book, chapter, original_text, source_url,
                   source_line_start, source_line_end, embedding, embedding_norm
            FROM chunks
        """):
            vector = decode_vector(row["embedding"], self.dimensions)
            score = sum(a * b for a, b in zip(query_vector, vector, strict=True)) / (
                query_norm * row["embedding_norm"]
            )
            results.append((score, row))
        results.sort(key=lambda item: item[0], reverse=True)
        return [{
            "score": round(score, 6),
            "source_id": row["source_id"],
            "book": row["book"],
            "chapter": row["chapter"],
            "excerpt": row["original_text"][:240],
            "source_url": row["source_url"],
            "source_line_start": row["source_line_start"],
            "source_line_end": row["source_line_end"],
        } for score, row in results[:limit]]

    @staticmethod
    def _keyword_score(chapter: str, text: str, keywords: list[str]) -> float:
        chapter_lower = chapter.casefold()
        text_lower = text.casefold()
        score = 0.0
        for keyword in keywords:
            value = " ".join(keyword.casefold().split())
            if len(value) < 2:
                continue
            if chapter_lower == value:
                score += 4.0
            elif value in chapter_lower:
                score += 2.0
            occurrences = text_lower.count(value)
            score += min(occurrences, 3) * 0.35
        return score

    def hybrid_candidates(self, query_vectors: list[list[float]], keywords: list[str],
                          limit: int = 20) -> list[dict]:
        if not query_vectors or limit < 1:
            raise ValueError("hybrid search input invalid")
        query_norms = [encode_vector(vector, self.dimensions)[1]
                       for vector in query_vectors]
        scored: list[dict] = []
        for row in self.connection.execute("""
            SELECT source_id, book, author, translator, chapter, language,
                   original_text, source_url, source_line_start, source_line_end,
                   source_file_sha256, rights_status, verified, quality_flags,
                   embedding, embedding_norm
            FROM chunks
        """):
            vector = decode_vector(row["embedding"], self.dimensions)
            vector_score = max(
                sum(a * b for a, b in zip(query_vector, vector, strict=True)) /
                (query_norm * row["embedding_norm"])
                for query_vector, query_norm in zip(query_vectors, query_norms, strict=True)
            )
            lexical_score = self._keyword_score(row["chapter"], row["original_text"], keywords)
            scored.append({
                "source_id": row["source_id"], "book": row["book"],
                "author": row["author"], "translator": row["translator"],
                "chapter": row["chapter"], "language": row["language"],
                "original_text": row["original_text"], "source_url": row["source_url"],
                "source_line_start": row["source_line_start"],
                "source_line_end": row["source_line_end"],
                "source_file_sha256": row["source_file_sha256"],
                "rights_status": row["rights_status"], "verified": bool(row["verified"]),
                "quality_flags": json.loads(row["quality_flags"]),
                "vector_score": vector_score, "lexical_score": lexical_score,
            })

        vector_rank = {
            item["source_id"]: rank for rank, item in enumerate(
                sorted(scored, key=lambda item: item["vector_score"], reverse=True), 1
            )
        }
        lexical_items = sorted(
            (item for item in scored if item["lexical_score"] > 0),
            key=lambda item: item["lexical_score"], reverse=True,
        )
        lexical_rank = {item["source_id"]: rank for rank, item in enumerate(lexical_items, 1)}
        for item in scored:
            item["hybrid_score"] = 1 / (60 + vector_rank[item["source_id"]])
            if item["source_id"] in lexical_rank:
                item["hybrid_score"] += 1 / (60 + lexical_rank[item["source_id"]])
            # Exact headings such as Deer/Fall should survive to the rerank set.
            item["hybrid_score"] += min(item["lexical_score"], 4.0) * 0.01
        scored.sort(key=lambda item: item["hybrid_score"], reverse=True)
        return scored[:limit]
