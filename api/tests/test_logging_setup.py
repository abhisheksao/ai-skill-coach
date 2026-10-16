"""Structured logging (T032): JSON line shape, x-request-id stamping via the
real app (client fixture), and setup_logging() idempotency -- previously
untested despite the code explicitly guarding against double-registration."""

import json
import logging

import pytest

from coach_core.logging_setup import JsonFormatter, setup_logging

pytestmark = [pytest.mark.foundations, pytest.mark.logging]


def make_record(msg: str = "hello", extra: dict | None = None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="skillcoach.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=None,
    )
    if extra:
        record.request_log = extra
    return record


def test_format_produces_valid_json_with_level_logger_message() -> None:
    entry = json.loads(JsonFormatter().format(make_record("hello")))
    assert entry["level"] == "info"
    assert entry["logger"] == "skillcoach.test"
    assert entry["message"] == "hello"


def test_format_merges_request_log_extra() -> None:
    entry = json.loads(
        JsonFormatter().format(
            make_record("request", extra={"request_id": "abc123", "status": 200})
        )
    )
    assert entry["request_id"] == "abc123"
    assert entry["status"] == 200


def test_format_without_extra_has_no_request_fields() -> None:
    entry = json.loads(JsonFormatter().format(make_record("plain")))
    assert "request_id" not in entry


def test_setup_logging_is_idempotent() -> None:
    setup_logging()
    setup_logging()
    root = logging.getLogger()
    json_handlers = [h for h in root.handlers if isinstance(h.formatter, JsonFormatter)]
    assert len(json_handlers) == 1


def test_request_middleware_stamps_response_header(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    request_id = response.headers["x-request-id"]
    assert len(request_id) == 12
    int(request_id, 16)  # raises ValueError if not valid hex
