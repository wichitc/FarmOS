"""Structured JSON logging (NFR-009: "services shall emit structured logs
with correlation/trace IDs"). `correlation_id_var` is a contextvar, not a
parameter threaded through every function signature - the same
cross-cutting-concern-via-context shape `core/deps.py::set_tenant_context`
already uses for RLS, applied here to logging instead of the DB session.
Any log statement anywhere in a request's call stack picks it up
automatically once `main.py`'s `correlation_id_middleware` sets it for
that request - no call site needs to know or pass it explicitly.
"""
import contextvars
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

correlation_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        correlation_id = correlation_id_var.get()
        if correlation_id:
            payload["correlation_id"] = correlation_id
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(level: int = logging.INFO) -> None:
    """Replaces the default handler on the root logger and on uvicorn's
    loggers with one JSON-formatted handler, so both application logs and
    uvicorn's own access/error logs come out structured. Call once, at
    process startup, before the app starts serving traffic."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers = [handler]
        logger.propagate = False


def set_correlation_id(correlation_id: Optional[str]) -> contextvars.Token:
    return correlation_id_var.set(correlation_id or "")


class CorrelationIdMiddleware:
    """Deliberately a raw ASGI middleware, not `@app.middleware("http")`
    (Starlette's `BaseHTTPMiddleware`): `BaseHTTPMiddleware` runs
    downstream processing in a way that does not reliably propagate a
    contextvar set *inside* one http-style middleware to the
    middleware/handlers below it (a documented Starlette limitation - a
    contextvar set before `call_next()` isn't guaranteed visible after
    it). A raw ASGI middleware runs the whole request in one coroutine
    with no such boundary, so setting the contextvar here - registered as
    the outermost middleware, wrapping everything else - makes it visible
    everywhere downstream, including inside `core/rate_limit.py`'s
    logging. Also stamps `scope["state"]["correlation_id"]` so
    `request.state.correlation_id` keeps working for code (like
    `main.py`'s exception handler) that reads it that way instead.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        correlation_id = headers.get(b"x-correlation-id", b"").decode() or str(uuid.uuid4())
        scope.setdefault("state", {})["correlation_id"] = correlation_id

        async def send_with_correlation_header(message):
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = response_headers
            await send(message)

        token = correlation_id_var.set(correlation_id)
        try:
            await self.app(scope, receive, send_with_correlation_header)
        finally:
            correlation_id_var.reset(token)
