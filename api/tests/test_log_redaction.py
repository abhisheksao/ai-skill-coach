"""Logging policy proof (005, research.md R14): a chat turn carrying a
sentinel string, and its own JWT, never leak into any log record --
structurally guaranteed by JsonFormatter's fixed field allowlist, proven
here by actually driving traffic through it. The ai_failure event (an LLM
failure) carries only endpoint/sub/intent_type/failure_class, never the
message that triggered it."""

import logging
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from coach_core.errors import LlmUnavailable
from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from tests.fakes import (
    FakeAnalytics,
    FakeBudget,
    FakeCadenceSchedule,
    FakeContextBuilder,
    FakeGraph,
    FakeIntentApply,
    FakeJwksClient,
    FakeLlm,
    FakeMessages,
)

pytestmark = [pytest.mark.hardening, pytest.mark.logging]

SESSION_ID = str(uuid.uuid4())
SENTINEL = "sentinel-xk392-do-not-log-me"


@pytest.fixture
def pipeline(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    app = create_app()
    fakes = SimpleNamespace(
        budget=FakeBudget(),
        llm=FakeLlm(reply="Hi there!"),
        messages=FakeMessages(language="en"),
        graph=FakeGraph(),
        context_builder=FakeContextBuilder(language="en"),
        intent_apply=FakeIntentApply(),
        cadence_schedule=FakeCadenceSchedule(),
        analytics=FakeAnalytics(),
    )
    app.state.services = fakes
    return TestClient(app, raise_server_exceptions=False), fakes


def _all_record_text(records: list[logging.LogRecord]) -> list[str]:
    texts = []
    for record in records:
        texts.append(record.getMessage())
        for attr in ("request_log", "ai_failure"):
            extra = getattr(record, attr, None)
            if extra:
                texts.append(str(extra))
    return texts


def test_sentinel_message_and_jwt_never_appear_in_any_log_record(
    pipeline, make_token, caplog
) -> None:
    client, _fakes = pipeline
    token = make_token(sub="user-1")

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/v1/chat",
            json={"message": SENTINEL, "session_id": SESSION_ID, "new_skill_name": "Swimming"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    texts = _all_record_text(caplog.records)
    assert not any(SENTINEL in t for t in texts)
    assert not any(token in t for t in texts)


def test_ai_failure_event_carries_endpoint_sub_intent_type_failure_class_never_the_message(
    pipeline, make_token, caplog
) -> None:
    client, fakes = pipeline
    fakes.llm.fail = LlmUnavailable()
    token = make_token(sub="user-1")

    with caplog.at_level(logging.DEBUG):
        response = client.post(
            "/v1/chat",
            json={"message": SENTINEL, "session_id": SESSION_ID, "new_skill_name": "Swimming"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 503
    ai_failure_records = [r for r in caplog.records if getattr(r, "ai_failure", None)]
    assert len(ai_failure_records) == 1
    payload = ai_failure_records[0].ai_failure
    assert payload == {
        "event": "ai_failure",
        "endpoint": "/v1/chat",
        "sub": "user-1",
        "intent_type": "wizard",
        "failure_class": "LlmUnavailable",
    }
    texts = _all_record_text(caplog.records)
    assert not any(SENTINEL in t for t in texts)
