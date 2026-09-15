"""Single-origin demo entry. Not a persistent/production data deployment."""
import os
from pathlib import Path

from fastapi.responses import FileResponse, JSONResponse


def attach_frontend(app, dist: Path):
    dist = dist.resolve()

    @app.middleware("http")
    async def configured_models_only(request, call_next):
        # Missing cloud secrets must never silently turn a real demo into mock output.
        if (request.method == "POST" and request.url.path.startswith("/api/v1/dreams")
                and not os.environ.get("DASHSCOPE_API_KEY", "").strip()):
            return JSONResponse({"error": {"code": "demo_not_configured", "message": "演示服务配置中，请稍后再试"}}, status_code=503)
        return await call_next(request)

    @app.get("/deployment-status")
    def deployment_status():
        return {"mode": "temporary_demo", "persistent": False,
                "model_configured": bool(os.environ.get("DASHSCOPE_API_KEY", "").strip())}

    @app.get("/{path:path}")
    def frontend(path: str):
        # Only dist assets can be served. Never fall back for private/API paths.
        if path.split("/", 1)[0] in {"api", "auth", "backend", "integrations", "deployment", "data"} or any(part.startswith(".") for part in path.split("/") if part):
            return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
        target = (dist / path).resolve()
        if not target.is_relative_to(dist):
            return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
        if target.is_file():
            return FileResponse(target, headers={"X-Content-Type-Options": "nosniff"})
        if Path(path).suffix:
            return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
        return FileResponse(dist / "index.html", headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
    return app
