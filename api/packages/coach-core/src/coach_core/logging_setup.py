"""Structured logging (T032).

One JSON line per request: request id, method, path, status, duration, and
the authenticated sub when known. Never message content, tokens, or secrets
— codified as a full policy in 005 (research.md R14), proven by
test_log_redaction.py.
"""

import json
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

# Extra-attribute names JsonFormatter merges into the JSON line, alongside
# level/logger/message. Two producers today: RequestLogMiddleware's
# per-request summary, and log_ai_failure's structured AI-failure event
# (005, R14) -- both are small, pre-validated dicts, never raw exception
# text or request/response bodies.
_STRUCTURED_EXTRA_ATTRS = ("request_log", "ai_failure")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for attr in _STRUCTURED_EXTRA_ATTRS:
            extra = getattr(record, attr, None)
            if extra:
                entry.update(extra)
        return json.dumps(entry, ensure_ascii=False)


_ai_failure_logger = logging.getLogger("skillcoach.ai_failure")


def log_ai_failure(endpoint: str, sub: str | None, intent_type: str, failure_class: str) -> None:
    """005, research.md R14: structured AI-failure event -- endpoint,
    pseudonymous sub, intent type, and failure class ONLY, never message
    bodies or secrets. Answers US4 scenario 2 (debug an AI failure from
    logs alone, no transcript access needed)."""
    _ai_failure_logger.warning(
        "ai_failure",
        extra={
            "ai_failure": {
                "event": "ai_failure",
                "endpoint": endpoint,
                "sub": sub,
                "intent_type": intent_type,
                "failure_class": failure_class,
            }
        },
    )


def setup_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers if h.formatter):
        root.addHandler(handler)
    root.setLevel(logging.INFO)


_request_logger = logging.getLogger("skillcoach.request")


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        _request_logger.info(
            "request",
            extra={
                "request_log": {
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                    "sub": getattr(request.state, "sub", None),
                }
            },
        )
        response.headers["x-request-id"] = request_id
        return response
