"""POST /v1/intents/apply (User Story 7) — happy path for complete_step/
log_checkin, source always forced to ui_tap regardless of request body
(FR-016), a validation failure surfaces directly with no retry (FR-015),
and zero LLM calls (SC-007, verified by there being no LlmService on the
fake services container at all — an accidental call would AttributeError,
not silently succeed)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from skillcoach_api.services.intent_apply import ApplyResult, IntentApplyService
from tests.fakes import FakeJwksClient

pytestmark = [pytest.mark.progress_notifications, pytest.mark.checkins]

SKILL = SimpleNamespace(
    id="skill-1",
    plan=SimpleNamespace(
        steps=[
            SimpleNamespace(order=1, description="Float and glide"),
            SimpleNamespace(order=2, description="Kick drills"),
        ]
    ),
)


class FakeSkills:
    def __init__(self, detail=None) -> None:
        self.detail = detail

    async def get_skill(self, _user_id: str, _skill_id: str):
        return self.detail


class FakeTx:
    def __init__(self) -> None:
        self.queries: list[tuple[str, dict]] = []

    async def run(self, query: str, **params) -> None:
        self.queries.append((query, params))


class FakeSession:
    def __init__(self, committed: list) -> None:
        self._committed = committed

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def execute_write(self, tx_func):
        tx = FakeTx()
        await tx_func(tx)
        self._committed.extend(tx.queries)


class FakeDriver:
    def __init__(self) -> None:
        self.committed: list[tuple[str, dict]] = []

    def session(self) -> FakeSession:
        return FakeSession(self.committed)


@pytest.fixture
def checkins_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    return create_app()


def _wire(app, *, skill=SKILL):
    driver = FakeDriver()
    # No `llm`/`budget` attribute at all -- an accidental call anywhere in
    # this path would AttributeError immediately (SC-007), not silently
    # succeed the way a present-but-unused fake could.
    app.state.services = SimpleNamespace(
        skills=FakeSkills(detail=skill),
        intent_apply=IntentApplyService(driver),
    )
    return driver


def _post(client, token, skill_id="skill-1", intent=None):
    return client.post(
        "/v1/intents/apply",
        json={"skill_id": skill_id, "intent": intent},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_complete_step_happy_path(checkins_app, make_token) -> None:
    driver = _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    response = _post(
        client,
        make_token(sub="user-1"),
        intent={"type": "complete_step", "step_order": 1, "sentiment": "positive"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "checkin_id" in body
    assert "applied_at" in body
    query, params = driver.committed[0]
    assert "CREATE (c:CheckIn" in query
    assert params["outcome"] == "completed"
    assert params["step_order"] == 1


def test_log_checkin_happy_path(checkins_app, make_token) -> None:
    driver = _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    response = _post(
        client,
        make_token(sub="user-1"),
        intent={
            "type": "log_checkin",
            "step_order": 2,
            "outcome": "partial",
            "sentiment": "neutral",
        },
    )

    assert response.status_code == 200
    _, params = driver.committed[0]
    assert params["outcome"] == "partial"
    assert params["step_order"] == 2


def test_source_is_always_ui_tap_regardless_of_request_body(checkins_app, make_token) -> None:
    """FR-016: source is never a client-controllable field -- there isn't
    even a place to put one in the request schema, but this proves the
    written value regardless."""
    driver = _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    _post(
        client,
        make_token(sub="user-1"),
        intent={
            "type": "complete_step",
            "step_order": 1,
            "sentiment": "positive",
            "source": "conversation",  # extra field -- must be ignored, not honored
        },
    )

    _, params = driver.committed[0]
    assert params["source"] == "ui_tap"


def test_report_obstacle_is_rejected_conversation_only(checkins_app, make_token) -> None:
    """research.md R6: report_obstacle needs a coach response, so it's
    excluded from UiIntent -- a request naming it fails schema validation
    (422), not applied."""
    client = TestClient(checkins_app, raise_server_exceptions=False)
    _wire(checkins_app)

    response = _post(
        client,
        make_token(sub="user-1"),
        intent={
            "type": "report_obstacle",
            "step_order": 1,
            "obstacle": "keep sinking",
            "sentiment": "negative",
        },
    )

    assert response.status_code == 422


def test_validation_failure_surfaces_directly_with_no_retry(checkins_app, make_token) -> None:
    """FR-015: an invalid step_order (out of the 1-12 Pydantic range) is a
    plain 422 -- no retry loop exists on this path to fall back to."""
    driver = _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    response = _post(
        client,
        make_token(sub="user-1"),
        intent={"type": "complete_step", "step_order": 99, "sentiment": "positive"},
    )

    assert response.status_code == 422
    assert driver.committed == []  # no partial write


def test_step_order_outside_the_active_plan_is_rejected(checkins_app, make_token) -> None:
    driver = _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    response = _post(
        client,
        make_token(sub="user-1"),
        intent={"type": "complete_step", "step_order": 7, "sentiment": "positive"},
    )

    assert response.status_code == 500  # same as chat.py's equivalent guard
    assert driver.committed == []


def test_missing_or_not_owned_skill_404s(checkins_app, make_token) -> None:
    _wire(checkins_app, skill=None)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    response = _post(
        client,
        make_token(sub="user-1"),
        intent={"type": "complete_step", "step_order": 1, "sentiment": "positive"},
    )

    assert response.status_code == 404


def test_requires_auth(checkins_app) -> None:
    _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)

    response = client.post(
        "/v1/intents/apply",
        json={
            "skill_id": "skill-1",
            "intent": {"type": "complete_step", "step_order": 1, "sentiment": "positive"},
        },
    )
    assert response.status_code == 401


def test_double_tap_in_quick_succession_produces_two_independent_checkins_no_dedup_needed(
    checkins_app, make_token
) -> None:
    """Edge Case: rapid double-tap -- each call is an independent,
    validated apply through the same atomic pipeline as any other
    check-in; CheckIn is append-only by design (data-model.md), so two
    taps simply record two CheckIns, same as two conversational reports
    on the same day would (Edge Case in spec: same-day duplicates are all
    recorded, derived metrics de-duplicate at the streak layer, not by
    rejecting the write)."""
    driver = _wire(checkins_app)
    client = TestClient(checkins_app, raise_server_exceptions=False)
    token = make_token(sub="user-1")
    intent = {"type": "complete_step", "step_order": 1, "sentiment": "positive"}

    r1 = _post(client, token, intent=intent)
    r2 = _post(client, token, intent=intent)

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert len(driver.committed) == 2
    assert r1.json()["checkin_id"] != r2.json()["checkin_id"]


def test_apply_result_default_still_works_when_no_checkin_produced() -> None:
    """Documents ApplyResult's new field default explicitly."""
    assert ApplyResult().checkin_id is None
