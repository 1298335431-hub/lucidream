"""veFaaS entry: volatile database, private OAuth companion, one public port."""
import logging
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import secrets
import time


def main():
    root = Path(__file__).resolve().parent
    runtime = Path(tempfile.mkdtemp(prefix="lucidream-demo-"))
    # The current index adapter creates/validates schema, so give it a writable copy.
    shutil.copyfile(root / "data/knowledge/dream_sources.sqlite3", runtime / "knowledge.sqlite3")
    # Explicit demo defaults before importing the app (which opens SQLite).
    os.environ.update({
        "DREAMCARD_ENV": "production", "DREAMCARD_AUTH_ENABLED": "true",
        "DREAMCARD_MODEL_MODE": "aliyun", "DREAMCARD_IMAGE_QUOTA_TOTAL": "8",
        "DREAMCARD_DATABASE_PATH": str(runtime / "dreamcard.db"),
        "DREAMCARD_KNOWLEDGE_INDEX_PATH": str(runtime / "knowledge.sqlite3"),
        "DREAMCARD_ORIGINAL_KNOWLEDGE_CARDS_PATH": str(root / "data/knowledge/cards.jsonl"),
        "PYTHONDONTWRITEBYTECODE": "1",
    })
    os.environ.setdefault("DREAMCARD_CORS_ORIGINS", "")
    sys.path.insert(0, str(root / "backend"))
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "vendor"))
    # Ship only a checksum-verified Node archive. No network install at cold start.
    archive = root / "runtime/node.tar.gz"
    node = runtime / "node"
    with tarfile.open(archive, "r:gz") as tar:
        candidates = [m for m in tar.getmembers() if m.name.endswith("/bin/node") and m.isfile()]
        if len(candidates) != 1:
            raise RuntimeError("invalid Node runtime archive")
        with tar.extractfile(candidates[0]) as source, node.open("wb") as target:
            shutil.copyfileobj(source, target)
    node.chmod(0o700)
    companion = subprocess.Popen([str(node), str(root / "integrations/zhihu-login/server.mjs")],
                                 env={**os.environ, "PORT": "4173"},
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        import uvicorn
        from app.main import app
        from app.services.invite_auth import digest
        from demo_server import attach_frontend
        # A separately injected demo credential, never a bundled real account.
        code = os.environ.get("DREAMCARD_DEMO_INVITE_CODE", "").strip().upper()
        if code:
            with app.state.invite_auth.connect() as db:
                db.execute("INSERT OR IGNORE INTO invite_accounts(id, code_hash, created_at) VALUES(?,?,?)",
                           (secrets.token_hex(16), digest(code), time.time()))
        # Only emit the deliberately redacted request logger, not HTTP SDK debug logs.
        request_logger = logging.getLogger("dreamcard.requests")
        request_logger.setLevel(logging.INFO)
        request_logger.addHandler(logging.StreamHandler())
        request_logger.propagate = False

        @app.get("/deployment-companion")
        def companion_status():
            return {"running": companion.poll() is None}

        uvicorn.run(attach_frontend(app, root / "dist"), host="0.0.0.0", port=8000,
                    access_log=False, proxy_headers=False)
    finally:
        companion.terminate()
        try:
            companion.wait(timeout=5)
        except subprocess.TimeoutExpired:
            companion.kill()
            companion.wait()
        # Exact newly-created temporary directory only; no user or previous database.
        shutil.rmtree(runtime)


if __name__ == "__main__":
    main()
