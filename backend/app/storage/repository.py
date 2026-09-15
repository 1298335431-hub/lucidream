import json
import sqlite3
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.schemas.dream import (
    ClarificationQuestion,
    DreamSessionResponse,
    DreamSymbols,
)


SCHEMA_VERSION = 11


class DreamRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("CREATE TABLE IF NOT EXISTS image_events (id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL, revision INTEGER NOT NULL, stage TEXT NOT NULL, code TEXT, request_id TEXT, task_id TEXT, created_at TEXT NOT NULL)")
            connection.execute("CREATE TABLE IF NOT EXISTS image_assets (session_id TEXT NOT NULL, revision INTEGER NOT NULL, source_hash TEXT NOT NULL, content BLOB NOT NULL, media_type TEXT NOT NULL, PRIMARY KEY(session_id, revision, source_hash))")
            connection.execute("CREATE TABLE IF NOT EXISTS image_leases (session_id TEXT NOT NULL, revision INTEGER NOT NULL, token TEXT NOT NULL, expires_at REAL NOT NULL, PRIMARY KEY(session_id, revision))")
            connection.execute("CREATE TABLE IF NOT EXISTS image_choices (session_id TEXT NOT NULL, revision INTEGER NOT NULL, source_hash TEXT NOT NULL, PRIMARY KEY(session_id, revision))")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS dream_sessions (
                    id TEXT PRIMARY KEY,
                    dream_text TEXT NOT NULL,
                    status TEXT NOT NULL,
                    symbols_json TEXT NOT NULL,
                    clarification_json TEXT,
                    clarification_answer TEXT,
                    safety_message TEXT,
                    revision INTEGER NOT NULL,
                    model_mode TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS interpretation_generations (
                    session_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('processing', 'completed', 'failed')),
                    result_json TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, revision)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS image_generations (
                    session_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('processing', 'completed', 'failed')),
                    task_id TEXT,
                    image_url TEXT,
                    error_code TEXT,
                    quality_retry_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, revision)
                )
                """
            )
            session_columns = {row["name"] for row in connection.execute("PRAGMA table_info(dream_sessions)").fetchall()}
            if "owner_id" not in session_columns:
                connection.execute("ALTER TABLE dream_sessions ADD COLUMN owner_id TEXT")
            connection.execute("CREATE INDEX IF NOT EXISTS dream_owner_idx ON dream_sessions(owner_id, created_at)")
            if "character_form" not in session_columns:
                connection.execute("ALTER TABLE dream_sessions ADD COLUMN character_form TEXT NOT NULL DEFAULT ''")
            if "character_appearance" not in session_columns:
                connection.execute("ALTER TABLE dream_sessions ADD COLUMN character_appearance TEXT NOT NULL DEFAULT 'unspecified'")
            image_columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(image_generations)").fetchall()
            }
            if "quality_retry_count" not in image_columns:
                connection.execute(
                    "ALTER TABLE image_generations "
                    "ADD COLUMN quality_retry_count INTEGER NOT NULL DEFAULT 0"
                )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS original_knowledge_shadow_runs (
                    session_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    fallback INTEGER NOT NULL CHECK(fallback IN (0, 1)),
                    hits_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(session_id, revision)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS original_knowledge_shadow_metrics (
                    metric_id TEXT PRIMARY KEY,
                    fallback INTEGER NOT NULL CHECK(fallback IN (0, 1)),
                    hits_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            migrated = connection.execute(
                "SELECT value FROM metadata WHERE key = 'shadow_metrics_migrated_v4'"
            ).fetchone()
            if migrated is None:
                # Move pre-v4 live observations into an anonymous aggregate table.
                # The new table deliberately has no session_id, revision or dream text.
                legacy_rows = connection.execute(
                    "SELECT fallback, hits_json, created_at FROM original_knowledge_shadow_runs"
                ).fetchall()
                connection.executemany(
                    """
                    INSERT INTO original_knowledge_shadow_metrics(
                        metric_id, fallback, hits_json, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    [
                        (str(uuid4()), row["fallback"], row["hits_json"], row["created_at"])
                        for row in legacy_rows
                    ],
                )
                connection.execute(
                    "INSERT INTO metadata(key, value) VALUES('shadow_metrics_migrated_v4', '1')"
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def create(
        self,
        dream_text: str,
        status: str,
        symbols: DreamSymbols,
        clarification: ClarificationQuestion | None,
        model_mode: str,
        safety_message: str | None = None,
        owner_id: str | None = None,
    ) -> DreamSessionResponse:
        now = datetime.now(UTC).isoformat()
        session_id = str(uuid4())
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO dream_sessions(
                    id, dream_text, status, symbols_json, clarification_json,
                    clarification_answer, safety_message, revision, model_mode,
                    created_at, updated_at, owner_id
                ) VALUES (?, ?, ?, ?, ?, NULL, ?, 1, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    dream_text,
                    status,
                    symbols.model_dump_json(),
                    clarification.model_dump_json() if clarification else None,
                    safety_message,
                    model_mode,
                    now,
                    now,
                    owner_id,
                ),
            )
        return self.get(session_id)

    def get(self, session_id: str) -> DreamSessionResponse:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM dream_sessions WHERE id = ?", (session_id,)
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return self._deserialize(row)

    def update_symbols(
        self,
        session_id: str,
        symbols: DreamSymbols,
        clarification_answer: str | None,
        character_appearance: str = "unspecified",
        character_form: str = "",
    ) -> DreamSessionResponse:
        current = self.get(session_id)
        if current.status == "safety_interrupted":
            raise ValueError("安全中断的会话不能继续生成")
        answer = clarification_answer.strip() if clarification_answer else None
        if current.clarification and not answer:
            status = "awaiting_clarification"
        else:
            status = "ready_to_generate"
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE dream_sessions
                SET symbols_json = ?, clarification_answer = ?, status = ?,
                    revision = revision + 1, updated_at = ?, character_appearance = ?, character_form = ?
                WHERE id = ?
                """,
                (symbols.model_dump_json(), answer, status, now, character_appearance, character_form, session_id),
            )
        return self.get(session_id)

    def delete(self, session_id: str) -> bool:
        with self._write_lock, self._connect() as connection:
            for table in ("image_events", "image_assets", "image_leases", "image_choices"):
                connection.execute(f"DELETE FROM {table} WHERE session_id = ?", (session_id,))
            connection.execute(
                "DELETE FROM image_generations WHERE session_id = ?", (session_id,)
            )
            connection.execute(
                "DELETE FROM interpretation_generations WHERE session_id = ?", (session_id,)
            )
            connection.execute(
                "DELETE FROM original_knowledge_shadow_runs WHERE session_id = ?",
                (session_id,),
            )
            result = connection.execute(
                "DELETE FROM dream_sessions WHERE id = ?", (session_id,)
            )
        return result.rowcount > 0

    def record_original_knowledge_shadow(
        self,
        session_id: str,
        revision: int,
        fallback: bool,
        hits: list[dict],
    ) -> None:
        """Persist shadow results without duplicating the dream or symbol query."""
        now = datetime.now(UTC).isoformat()
        payload = json.dumps(hits, ensure_ascii=False, separators=(",", ":"))
        with self._write_lock, self._connect() as connection:
            existing = connection.execute(
                """
                SELECT 1 FROM original_knowledge_shadow_runs
                WHERE session_id = ? AND revision = ?
                """,
                (session_id, revision),
            ).fetchone()
            if existing is None:
                connection.execute(
                    """
                    INSERT INTO original_knowledge_shadow_runs(
                        session_id, revision, fallback, hits_json, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, revision, int(fallback), payload, now),
                )
                connection.execute(
                    """
                    INSERT INTO original_knowledge_shadow_metrics(
                        metric_id, fallback, hits_json, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (str(uuid4()), int(fallback), payload, now),
                )
            else:
                # Keep the live per-session view current without duplicating the
                # anonymous event used for aggregate evaluation.
                connection.execute(
                    """
                    UPDATE original_knowledge_shadow_runs
                    SET fallback = ?, hits_json = ?, created_at = ?
                    WHERE session_id = ? AND revision = ?
                    """,
                    (int(fallback), payload, now, session_id, revision),
                )

    def get_original_knowledge_shadow(
        self, session_id: str, revision: int
    ) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT fallback, hits_json, created_at
                FROM original_knowledge_shadow_runs
                WHERE session_id = ? AND revision = ?
                """,
                (session_id, revision),
            ).fetchone()
        if row is None:
            return None
        return {
            "fallback": bool(row["fallback"]),
            "hits": json.loads(row["hits_json"]),
            "created_at": row["created_at"],
        }

    def summarize_original_knowledge_shadow(self) -> dict:
        """Return aggregate-only shadow metrics; never include dream or symbol text."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT fallback, hits_json FROM original_knowledge_shadow_metrics"
            ).fetchall()
        card_hits: dict[str, int] = {}
        fallback_count = 0
        for row in rows:
            fallback_count += int(bool(row["fallback"]))
            try:
                hits = json.loads(row["hits_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            for hit in hits if isinstance(hits, list) else []:
                card_id = hit.get("card_id") if isinstance(hit, dict) else None
                if isinstance(card_id, str) and card_id:
                    card_hits[card_id] = card_hits.get(card_id, 0) + 1
        total = len(rows)
        return {
            "total_runs": total,
            "matched_runs": total - fallback_count,
            "fallback_runs": fallback_count,
            "match_rate": round((total - fallback_count) / total, 4) if total else None,
            "card_hits": dict(sorted(card_hits.items())),
            "includes_user_text": False,
            "model_calls": 0,
        }

    def get_generation(self, session_id: str, revision: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, result_json, error_code, created_at, updated_at
                FROM interpretation_generations
                WHERE session_id = ? AND revision = ?
                """,
                (session_id, revision),
            ).fetchone()
        return dict(row) if row is not None else None

    def begin_generation(self, session_id: str, revision: int) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO interpretation_generations(
                    session_id, revision, status, result_json, error_code,
                    created_at, updated_at
                ) VALUES (?, ?, 'processing', NULL, NULL, ?, ?)
                """,
                (session_id, revision, now, now),
            )
        return result.rowcount == 1

    def expire_generation(self, session_id: str, revision: int, timeout_seconds: float = 900) -> None:
        """Recover abandoned work lazily; never submit a new model call on reads."""
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """UPDATE interpretation_generations
                SET status = 'failed', error_code = 'generation_interrupted'
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                  AND (julianday('now') - julianday(updated_at)) * 86400 >= ?""",
                (session_id, revision, timeout_seconds),
            )

    def complete_generation(self, session_id: str, revision: int, result_json: str, *, started_at: str | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                UPDATE interpretation_generations
                SET status = 'completed', result_json = ?, error_code = NULL, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                  AND (? IS NULL OR updated_at = ?)
                """,
                (result_json, now, session_id, revision, started_at, started_at),
            )
        if result.rowcount != 1:
            raise RuntimeError("生成任务状态冲突")

    def fail_generation(self, session_id: str, revision: int, error_code: str, *, started_at: str | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE interpretation_generations
                SET status = 'failed', result_json = NULL, error_code = ?, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                  AND (? IS NULL OR updated_at = ?)
                """,
                (error_code[:100], now, session_id, revision, started_at, started_at),
            )

    def retry_generation(self, session_id: str, revision: int) -> bool:
        """Explicit retry only; callers must require a user-initiated request."""
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                UPDATE interpretation_generations
                SET status = 'processing', result_json = NULL, error_code = NULL, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'failed'
                """,
                (now, session_id, revision),
            )
        return result.rowcount == 1

    def get_image_generation(self, session_id: str, revision: int) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT status, task_id, image_url, error_code, quality_retry_count,
                       created_at, updated_at
                FROM image_generations
                WHERE session_id = ? AND revision = ?
                """,
                (session_id, revision),
            ).fetchone()
        return dict(row) if row is not None else None

    def begin_image_generation(self, session_id: str, revision: int) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                INSERT OR IGNORE INTO image_generations(
                    session_id, revision, status, task_id, image_url, error_code,
                    created_at, updated_at
                ) VALUES (?, ?, 'processing', NULL, NULL, NULL, ?, ?)
                """,
                (session_id, revision, now, now),
            )
        return result.rowcount == 1

    def attach_image_task(self, session_id: str, revision: int, task_id: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                UPDATE image_generations
                SET task_id = ?, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                """,
                (task_id, now, session_id, revision),
            )
        if result.rowcount != 1:
            raise RuntimeError("图片任务状态冲突")
        self.image_event(session_id, revision, "submitted", task_id=task_id)

    def begin_image_quality_retry(
        self, session_id: str, revision: int, completed_task_id: str
    ) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                UPDATE image_generations
                SET task_id = NULL, quality_retry_count = quality_retry_count + 1,
                    updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                  AND task_id = ? AND quality_retry_count < 1
                """,
                (now, session_id, revision, completed_task_id),
            )
        return result.rowcount == 1

    def complete_image_generation(self, session_id: str, revision: int, image_url: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                UPDATE image_generations
                SET status = 'completed', image_url = ?, error_code = NULL, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                """,
                (image_url, now, session_id, revision),
            )
        if result.rowcount != 1:
            raise RuntimeError("图片任务状态冲突")

    def fail_image_generation(self, session_id: str, revision: int, error_code: str) -> None:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            connection.execute(
                """
                UPDATE image_generations
                SET status = 'failed', error_code = ?, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'processing'
                """,
                (error_code[:100], now, session_id, revision),
            )
        self.image_event(session_id, revision, "failed", code=error_code)

    def retry_image_generation(self, session_id: str, revision: int) -> bool:
        now = datetime.now(UTC).isoformat()
        with self._write_lock, self._connect() as connection:
            result = connection.execute(
                """
                UPDATE image_generations
                SET status = 'processing', task_id = NULL,
                    error_code = NULL, quality_retry_count = quality_retry_count + 1, created_at = ?, updated_at = ?
                WHERE session_id = ? AND revision = ? AND status = 'failed'
                  AND quality_retry_count < 1
                  AND error_code NOT IN ('submission_unknown', 'generation_timeout')
                """,
                (now, now, session_id, revision),
            )
        return result.rowcount == 1

    def retain_image_candidate(self, session_id: str, revision: int, image_url: str) -> None:
        with self._write_lock, self._connect() as connection:
            connection.execute("UPDATE image_generations SET image_url = ? WHERE session_id = ? AND revision = ? AND status = 'processing'", (image_url, session_id, revision))

    def retry_image_review(self, session_id: str, revision: int) -> bool:
        with self._write_lock, self._connect() as connection:
            result = connection.execute("UPDATE image_generations SET status = 'processing', error_code = NULL, updated_at = ? WHERE session_id = ? AND revision = ? AND status = 'failed' AND error_code IN ('subject_review_unavailable', 'image_review_unavailable', 'generation_timeout') AND task_id IS NOT NULL", (datetime.now(UTC).isoformat(), session_id, revision))
        return result.rowcount == 1

    def image_event(self, session_id: str, revision: int, stage: str, *, code: str | None = None, request_id: str | None = None, task_id: str | None = None) -> None:
        # No prompts, signed image URLs, credentials, or raw provider messages.
        with self._connect() as connection:
            connection.execute("INSERT INTO image_events(session_id, revision, stage, code, request_id, task_id, created_at) VALUES (?,?,?,?,?,?,?)", (session_id, revision, stage[:80], (code or "")[:100], (request_id or "")[:128], (task_id or "")[:128], datetime.now(UTC).isoformat()))

    def save_image_asset(self, session_id: str, revision: int, url: str, content: bytes, media_type: str) -> None:
        with self._connect() as connection:
            connection.execute("INSERT OR IGNORE INTO image_assets VALUES (?,?,?,?,?)", (session_id, revision, hashlib.sha256(url.encode()).hexdigest(), content, media_type))

    def image_variants(self, session_id: str, revision: int) -> list[str]:
        with self._connect() as connection:
            return [row[0] for row in connection.execute("SELECT source_hash FROM image_assets WHERE session_id=? AND revision=? ORDER BY rowid", (session_id, revision))]

    def selected_image(self, session_id: str, revision: int) -> str | None:
        with self._connect() as connection:
            row = connection.execute("SELECT source_hash FROM image_choices WHERE session_id=? AND revision=?", (session_id, revision)).fetchone()
        return row[0] if row else None

    def select_image(self, session_id: str, revision: int, source_hash: str) -> bool:
        with self._connect() as connection:
            if not connection.execute("SELECT 1 FROM image_assets WHERE session_id=? AND revision=? AND source_hash=?", (session_id, revision, source_hash)).fetchone():
                return False
            connection.execute("INSERT INTO image_choices VALUES(?,?,?) ON CONFLICT(session_id, revision) DO UPDATE SET source_hash=excluded.source_hash", (session_id, revision, source_hash))
        return True

    def image_asset_by_hash(self, session_id: str, revision: int, source_hash: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT content, media_type FROM image_assets WHERE session_id=? AND revision=? AND source_hash=?", (session_id, revision, source_hash)).fetchone()
        return dict(row) if row else None

    def get_image_asset(self, session_id: str, revision: int, url: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute("SELECT content, media_type FROM image_assets WHERE session_id=? AND revision=? AND source_hash=?", (session_id, revision, hashlib.sha256(url.encode()).hexdigest())).fetchone()
        return dict(row) if row else None

    def claim_image_lease(self, session_id: str, revision: int) -> str | None:
        token = str(uuid4())
        with self._connect() as connection:
            result = connection.execute("INSERT INTO image_leases VALUES (?,?,?,?) ON CONFLICT(session_id,revision) DO UPDATE SET token=excluded.token, expires_at=excluded.expires_at WHERE image_leases.expires_at < ?", (session_id, revision, token, time.time() + 300, time.time()))
        return token if result.rowcount else None

    def release_image_lease(self, session_id: str, revision: int, token: str) -> None:
        with self._connect() as connection:
            connection.execute("DELETE FROM image_leases WHERE session_id=? AND revision=? AND token=?", (session_id, revision, token))

    def pending_images(self) -> list[tuple[str, int]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT session_id, revision FROM image_generations WHERE status='processing' ORDER BY updated_at LIMIT 20").fetchall()
        return [(row["session_id"], row["revision"]) for row in rows]

    @staticmethod
    def _deserialize(row: sqlite3.Row) -> DreamSessionResponse:
        try:
            raw_symbols = json.loads(row["symbols_json"])
            raw_clarification = (
                json.loads(row["clarification_json"])
                if row["clarification_json"]
                else None
            )
            symbols = DreamSymbols.model_validate(raw_symbols)
            clarification = (
                ClarificationQuestion.model_validate(raw_clarification)
                if raw_clarification
                else None
            )
        except (json.JSONDecodeError, ValueError) as error:
            raise RuntimeError("会话数据损坏") from error
        return DreamSessionResponse(
            id=row["id"],
            dream_text=row["dream_text"],
            status=row["status"],
            symbols=symbols,
            clarification=clarification,
            clarification_answer=row["clarification_answer"],
            character_appearance=row["character_appearance"],
            character_form=row["character_form"],
            safety_message=row["safety_message"],
            revision=row["revision"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            model_mode=row["model_mode"],
        )
