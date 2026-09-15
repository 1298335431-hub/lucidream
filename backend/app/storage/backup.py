"""Consistent SQLite snapshots. Never replace an existing database or backup.

Snapshots contain private records and must be kept in access-controlled storage.
This module does not provision cloud storage or provide multi-instance durability.
"""
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


REQUIRED_TABLES = {"dream_sessions", "metadata", "invite_accounts", "image_quota_usage", "image_assets"}


def validate_database(connection: sqlite3.Connection) -> None:
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise ValueError("数据库完整性检查失败")
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not REQUIRED_TABLES.issubset(tables):
        raise ValueError("不是完整的梦卡数据库")


def snapshot_database(source: Path, destination: Path, *, restore: bool = False) -> None:
    """Online backup; restore only into a new path, with login sessions revoked."""
    source, destination = Path(source).resolve(), Path(destination).absolute()
    if not source.is_file():
        raise ValueError("源数据库不存在")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("目标已存在，拒绝覆盖")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".dreamcard-snapshot-", dir=destination.parent)
    os.close(fd)
    try:
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=10)) as src:
            with closing(sqlite3.connect(temporary)) as dest:
                src.backup(dest)
                validate_database(dest)
                if restore:
                    # Do not restore a session that may have been revoked after the snapshot.
                    dest.execute("DELETE FROM auth_sessions")
                    dest.commit()
                validate_database(dest)
        with open(temporary, "rb") as stream:
            os.fsync(stream.fileno())
        # Atomic no-clobber publication, including against competing backup jobs.
        os.link(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        os.unlink(temporary)
