"""Demo entry checks without importing the real application's local database."""
import importlib.util
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient


def demo_app(tmp_path):
    module_path = Path(__file__).resolve().parents[2] / "deployment/demo_server.py"
    spec = importlib.util.spec_from_file_location("demo_server", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<h1>demo</h1>")
    (dist / "image.png").write_bytes(b"demo-image")
    (tmp_path / "secret.txt").write_text("must-not-serve")
    app = FastAPI()
    @app.get("/api/v1/health")
    def health():
        return {"ok": True}
    return module.attach_frontend(app, dist)


def test_only_frontend_assets_are_public(tmp_path):
    with TestClient(demo_app(tmp_path)) as client:
        assert client.get("/").text == "<h1>demo</h1>"
        assert client.get("/record").status_code == 200
        assert client.get("/image.png").content == b"demo-image"
        assert client.get("/api/v1/health").json() == {"ok": True}
        for path in ("/.env", "/backend/app/main.py", "/data/dreamcard.db", "/api/login/status", "/integrations/zhihu-login/hackathon.config.json", "/auth/unknown", "/%2e%2e/secret.txt", "/missing.png"):
            assert client.get(path).status_code == 404


def test_demo_without_keys_is_not_mock_generation(tmp_path, monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with TestClient(demo_app(tmp_path)) as client:
        status = client.get("/deployment-status").json()
        assert status == {"mode": "temporary_demo", "persistent": False, "model_configured": False}
        response = client.post("/api/v1/dreams/extract", json={"dream_text": "hello"})
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "demo_not_configured"
