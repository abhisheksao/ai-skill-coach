"""Contract tests 5–7 for POST /v1/chat (contracts/api.md), extended for
002: skill_id/new_skill_name threading, wizard-completion resolving a
skill_id, and ordinary skill conversations."""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from coach_core.errors import LlmUnavailable, error_body
from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from skillcoach_api.models.intents import CreatePlanIntent, CreateSkillIntent, StepPayload
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

pytestmark = [pytest.mark.wizard_plan, pytest.mark.chat, pytest.mark.hardening]

SESSION_ID = str(uuid.uuid4())


@pytest.fixture
def pipeline(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    app = create_app()
    fakes = SimpleNamespace(
        budget=FakeBudget(),
        llm=FakeLlm(reply="Hi there!"),
        messages=FakeMessages(language="hi"),
        graph=FakeGraph(),
        context_builder=FakeContextBuilder(language="hi"),
        intent_apply=FakeIntentApply(),
        cadence_schedule=FakeCadenceSchedule(),
        analytics=FakeAnalytics(),
    )
    app.state.services = fakes
    return TestClient(app, raise_server_exceptions=False), fakes


def _post(client, token, message="hello coach", skill_id=None, new_skill_name=None, modality=None):
    body = {"message": message, "session_id": SESSION_ID}
    if skill_id is not None:
        body["skill_id"] = skill_id
    if new_skill_name is not None:
        body["new_skill_name"] = new_skill_name
    if modality is not None:
        body["modality"] = modality
    return client.post("/v1/chat", json=body, headers={"Authorization": f"Bearer {token}"})


def test_contract_5_happy_path_wizard_turn(pipeline, make_token) -> None:
    client, fakes = pipeline
    response = _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hi there!"
    assert body["session_id"] == SESSION_ID
    assert body["skill_id"] is None  # no create_skill emitted this turn
    assert body["intents"] == []

    # lazy (:User) reconciliation ran (T029), budget consulted
    assert fakes.graph.calls == ["user-1"]
    assert fakes.budget.calls == ["user-1"]
    assert fakes.llm.calls == [("wizard", "hello coach", "Swimming", "hi")]
    assert len(fakes.messages.inserted) == 1
    turn = fakes.messages.inserted[0]
    assert turn["user_id"] == "user-1"
    assert turn["session_id"] == SESSION_ID
    assert turn["skill_id"] is None
    assert turn["user_text"] == "hello coach"
    assert turn["assistant_text"] == "Hi there!"


def test_session_started_emitted_on_the_first_message_of_a_session(pipeline, make_token) -> None:
    """005, research.md R8: session boundary = the turn where
    ContextBuilder reports zero prior user turns."""
    client, fakes = pipeline
    _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert ("session_started", "user-1", {"skill_id": None}) in fakes.analytics.emitted


def test_session_started_not_emitted_on_a_later_turn_in_the_same_session(
    pipeline, make_token
) -> None:
    client, fakes = pipeline
    fakes.context_builder.turn_count = 3
    _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert all(e[0] != "session_started" for e in fakes.analytics.emitted)


def test_intent_validation_failed_emitted_on_a_degraded_turn(pipeline, make_token) -> None:
    """005, research.md R8: llm.py's degraded-turn sentinel reply is the
    only signal chat.py has that validation retries were exhausted."""
    client, fakes = pipeline
    fakes.llm.reply = "errors.validation"
    _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert ("intent_validation_failed", "user-1", {"endpoint": "/v1/chat", "attempts": 3}) in (
        fakes.analytics.emitted
    )


def test_intent_validation_failed_not_emitted_on_a_normal_turn(pipeline, make_token) -> None:
    client, fakes = pipeline
    _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert all(e[0] != "intent_validation_failed" for e in fakes.analytics.emitted)


def test_analytics_failure_never_fails_the_chat_request(rsa_key, monkeypatch, make_token) -> None:
    """005, plan.md note 5: analytics is fire-and-forget -- wire the REAL
    AnalyticsService (not the test double) against a rest client whose
    insert always raises, and prove the chat turn still succeeds."""
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )

    class FailingInsertRest:
        async def insert(self, table: str, rows: list[dict]) -> None:
            raise RuntimeError("PostgREST unreachable")

    from coach_core.analytics import AnalyticsService

    app = create_app()
    app.state.services = SimpleNamespace(
        budget=FakeBudget(),
        llm=FakeLlm(reply="Hi there!"),
        messages=FakeMessages(language="hi"),
        graph=FakeGraph(),
        context_builder=FakeContextBuilder(language="hi"),
        intent_apply=FakeIntentApply(),
        cadence_schedule=FakeCadenceSchedule(),
        analytics=AnalyticsService(FailingInsertRest()),
    )
    client = TestClient(app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert response.status_code == 200
    assert response.json()["reply"] == "Hi there!"


def test_wizard_completion_resolves_and_persists_skill_id(pipeline, make_token) -> None:
    client, fakes = pipeline
    fakes.llm.intents = [
        CreateSkillIntent(type="create_skill", name="Swimming"),
        CreatePlanIntent(
            type="create_plan",
            skill_name="Swimming",
            goal_statement="Swim 1km",
            target_date="2026-12-01",
            weekly_days=3,
            weekly_minutes_per_day=30,
            steps=[
                StepPayload(order=1, description="Float", cadence_per_week=3),
                StepPayload(order=2, description="Kick", cadence_per_week=3),
                StepPayload(order=3, description="Stroke", cadence_per_week=2),
            ],
        ),
    ]
    new_skill_id = str(uuid.uuid4())
    fakes.intent_apply.created_skill_id = new_skill_id

    response = _post(
        client, make_token(sub="user-1"), message="yes that's right", new_skill_name="Swimming"
    )

    body = response.json()
    assert body["skill_id"] == new_skill_id
    assert len(body["intents"]) == 2
    assert fakes.intent_apply.applied[0][1] == "user-1"
    assert fakes.messages.inserted[0]["skill_id"] == new_skill_id


def test_suggested_replies_pass_through_to_response(pipeline, make_token) -> None:
    client, fakes = pipeline
    fakes.llm.suggested_replies = ["Beginner", "Some experience", "Intermediate", "Advanced"]

    response = _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert response.status_code == 200
    assert response.json()["suggested_replies"] == [
        "Beginner",
        "Some experience",
        "Intermediate",
        "Advanced",
    ]


def test_suggested_replies_empty_by_default(pipeline, make_token) -> None:
    client, _ = pipeline
    response = _post(client, make_token(sub="user-1"), new_skill_name="Swimming")
    assert response.json()["suggested_replies"] == []


def test_ongoing_skill_conversation_uses_coaching_turn(pipeline, make_token) -> None:
    client, fakes = pipeline
    skill_id = str(uuid.uuid4())
    response = _post(client, make_token(sub="user-1"), message="how am I doing", skill_id=skill_id)

    assert response.status_code == 200
    assert response.json()["skill_id"] == skill_id
    assert fakes.llm.calls == [("coaching", "how am I doing", "hi")]
    assert fakes.context_builder.calls == [("user-1", skill_id, SESSION_ID)]


@pytest.mark.voice_layer
def test_modality_defaults_to_chat(pipeline, make_token) -> None:
    """FR-005/003 T003: omitting modality stores 'chat', matching 001/002
    behavior exactly (modality has always been hardcoded to 'chat' until
    now — this proves the default is preserved once it's no longer
    hardcoded)."""
    client, fakes = pipeline
    response = _post(client, make_token(sub="user-1"), new_skill_name="Swimming")

    assert response.status_code == 200
    assert fakes.messages.inserted[0]["modality"] == "chat"


@pytest.mark.voice_layer
def test_modality_voice_persists(pipeline, make_token) -> None:
    """003 T003: a voice-originated turn stores modality='voice' (FR-005
    — identical to a chat turn except this one field)."""
    client, fakes = pipeline
    response = _post(client, make_token(sub="user-1"), new_skill_name="Swimming", modality="voice")

    assert response.status_code == 200
    assert fakes.messages.inserted[0]["modality"] == "voice"


def test_contract_6_budget_exhausted_is_a_200_coach_turn(pipeline, make_token) -> None:
    """005, contracts/api.md R2: budget exhaustion is no longer a raw 429 --
    it's an ordinary 200 chat turn with a `budget` object, zero LLM calls,
    and IS persisted (like the degraded-validation turn) so the transcript
    stays honest about what the user saw."""
    client, fakes = pipeline
    resets_at = datetime(2026, 7, 19, tzinfo=UTC)
    fakes.budget.over_budget = True
    fakes.budget.resets_at = resets_at

    response = _post(client, make_token(sub="user-1"))

    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "errors.budget_exhausted_reply"
    assert body["intents"] == []
    assert body["budget"] == {"exhausted": True, "resets_at": "2026-07-19T00:00:00Z"}
    assert fakes.llm.calls == []  # no LLM call
    assert len(fakes.messages.inserted) == 1
    assert fakes.messages.inserted[0]["assistant_text"] == "errors.budget_exhausted_reply"


def test_contract_6_blocked_user_gets_same_turn_without_resets_at(pipeline, make_token) -> None:
    """Contracts/api.md: the kill switch (user_limits.blocked) is
    deliberately indistinguishable from ordinary exhaustion to the client,
    except resets_at is omitted (no automatic reset)."""
    client, fakes = pipeline
    fakes.budget.over_budget = True
    fakes.budget.resets_at = None

    response = _post(client, make_token())

    assert response.status_code == 200
    body = response.json()
    assert body["budget"] == {"exhausted": True, "resets_at": None}


def test_budget_absent_on_a_normal_turn(pipeline, make_token) -> None:
    client, _ = pipeline
    response = _post(client, make_token(), new_skill_name="Swimming")
    assert response.json()["budget"] is None


def test_contract_7_llm_failure_persists_nothing(pipeline, make_token) -> None:
    client, fakes = pipeline
    fakes.llm.fail = LlmUnavailable()
    response = _post(client, make_token())

    assert response.status_code == 503
    assert response.json() == error_body("llm_unavailable", "errors.llm_unavailable")
    assert fakes.messages.inserted == []


def test_validation_error_envelope(pipeline, make_token) -> None:
    client, _ = pipeline
    response = client.post(
        "/v1/chat",
        json={"message": "", "session_id": SESSION_ID},
        headers={"Authorization": f"Bearer {make_token()}"},
    )
    assert response.status_code == 422
    assert response.json() == error_body("validation_error", "errors.validation")


def test_requires_auth(pipeline) -> None:
    client, _ = pipeline
    response = client.post("/v1/chat", json={"message": "x", "session_id": SESSION_ID})
    assert response.status_code == 401
