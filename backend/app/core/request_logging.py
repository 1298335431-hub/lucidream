"""Request diagnostics without query strings, credentials or dream content."""
import json
import logging
import time
from uuid import uuid4

from fastapi.responses import JSONResponse


logger = logging.getLogger("dreamcard.requests")


def install_request_logging(app):
    @app.middleware("http")
    async def track(request, call_next):
        trace_id = uuid4().hex
        request.state.trace_id = trace_id
        started = time.monotonic()
        try:
            response = await call_next(request)
        except Exception:
            # No exception repr/traceback: upstream messages may carry credentials.
            response = JSONResponse(status_code=500, content={"error": {
                "code": "internal_error", "message": "服务暂时异常，请稍后重试", "trace_id": trace_id,
            }})
        response.headers["X-Request-ID"] = trace_id
        route = request.scope.get("route")
        event = {"event": "http_request", "trace_id": trace_id,
                 "method": request.method, "route": getattr(route, "path", "unmatched"),
                 "status": response.status_code, "duration_ms": round((time.monotonic() - started) * 1000)}
        logger.log(logging.ERROR if response.status_code >= 500 else logging.INFO, json.dumps(event))
        return response
