"""T010: route-level check-in tests using REAL LlmService/ContextBuilder/
IntentApplyService, faked only at the I/O boundary — proves routes/chat.py
actually threads `valid_step_orders`/`source` through for the three new
check-in intents (log_checkin/report_obstacle/complete_step), applying end
to end through POST /v1/chat and persisting the resulting CheckIn (mirrors
test_chat_wizard.py's real-route style).
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from skillcoach_api.models.chat import ChatTurn
from skillcoach_api.models.intents import (
    CompleteStepIntent,
    LogCheckinIntent,
    ReportObstacleIntent,
)
from skillcoach_api.models.skills import GoalDetail, PlanDetail, SkillDetail, StepDetail
from skillcoach_api.services.context_builder import ContextBuilder
from skillcoach_api.services.intent_apply import IntentApplyService
from skillcoach_api.services.llm import LlmService
from tests.fakes import FakeAnalytics, FakeBudget, FakeGraph, FakeJwksClient, FakeProgress

pytestmark = [pytest.mark.progress_notifications, pytest.mark.chat, pytest.mark.checkins]

SESSION_ID = str(uuid.uuid4())
SKILL_ID = str(uuid.uuid4())

SKILL = SkillDetail(
    id=SKILL_ID,
    name="Swimming",
    goal=GoalDetail(statement="Swim 1km", target_date="2026-12-01"),
    plan=PlanDetail(
        id="plan-1",
        generation=0,
        steps=[
            StepDetail(order=1, description="Float and glide", cadence_per_week=3),
            StepDetail(order=2, description="Kick drills", cadence_per_week=3),
        ],
    ),
)


class FakeRunnable:
    """Mimics with_structured_output(ChatTurn, include_raw=True)'s
    {raw, parsed, parsing_error} shape (005, research.md R7)."""

    def __init__(self, results: list) -> None:
        self._results = iter(results)
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        result = next(self._results)
        return {"raw": None, "parsed": result, "parsing_error": None}


class FakeMessagesForContext:
    def __init__(self) -> None:
        self.inserted: list[dict] = []

    async def profile_language(self, _user_id: str) -> str:
        return "en"

    async def profile_timezone(self, _user_id: str) -> str:
        return "UTC"

    async def recent_messages(self, _session_id: str, limit: int = 20) -> list[dict]:
        return []

    async def count_user_turns(self, _session_id: str) -> int:
        return 3

    async def insert_turn(
        self, user_id, session_id, skill_id, user_text, assistant_text, modality="chat"
    ) -> None:
        self.inserted.append({"user_id": user_id, "session_id": session_id, "skill_id": skill_id})


class FakeSkillsForContext:
    async def get_skill(self, _user_id: str, _skill_id: str):
        return SKILL

    async def recent_session_summaries(self, _user_id: str, _skill_id: str, _limit: int):
        return []

    async def goal_revision_history(self, _user_id: str, _skill_id: str):
        return []


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
def checkin_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    return create_app()


def _wire(app, *, llm_results: list):
    messages = FakeMessagesForContext()
    driver = FakeDriver()
    runnable = FakeRunnable(llm_results)
    fakes = SimpleNamespace(
        budget=FakeBudget(),
        graph=FakeGraph(),
        messages=messages,
        context_builder=ContextBuilder(messages, FakeSkillsForContext(), FakeProgress()),
        llm=LlmService(runnable, retry_wait_multiplier=0.001),
        intent_apply=IntentApplyService(driver),
        analytics=FakeAnalytics(),
    )
    app.state.services = fakes
    return fakes, driver, runnable


def _post(client, token, message: str):
    return client.post(
        "/v1/chat",
        json={"message": message, "session_id": SESSION_ID, "skill_id": SKILL_ID},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_log_checkin_intent_persists_a_checkin_through_the_real_route(
    checkin_app, make_token
) -> None:
    intent = LogCheckinIntent(
        type="log_checkin", step_order=1, outcome="partial", sentiment="positive"
    )
    turn = ChatTurn(reply="Nice progress on the float drills!", intents=[intent])
    fakes, driver, _ = _wire(checkin_app, llm_results=[turn])
    client = TestClient(checkin_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"), "did my float drills today")

    assert response.status_code == 200
    assert len(driver.committed) == 1
    query, params = driver.committed[0]
    assert "CREATE (c:CheckIn" in query
    assert params["outcome"] == "partial"
    assert params["step_order"] == 1
    assert params["source"] == "conversation"
    assert params["skill_id"] == SKILL_ID
    assert fakes.messages.inserted[0]["skill_id"] == SKILL_ID


def test_complete_step_intent_persists_a_completed_checkin(checkin_app, make_token) -> None:
    intent = CompleteStepIntent(type="complete_step", step_order=2, sentiment="positive")
    turn = ChatTurn(reply="Kick drills done — great work!", intents=[intent])
    _, driver, _ = _wire(checkin_app, llm_results=[turn])
    client = TestClient(checkin_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"), "finished the kick drills")

    assert response.status_code == 200
    _, params = driver.committed[0]
    assert params["outcome"] == "completed"
    assert params["step_order"] == 2


def test_report_obstacle_intent_persists_an_obstacle_checkin(checkin_app, make_token) -> None:
    intent = ReportObstacleIntent(
        type="report_obstacle", step_order=1, obstacle="keep sinking", sentiment="negative"
    )
    turn = ChatTurn(reply="Let's try a pull buoy next time.", intents=[intent])
    _, driver, _ = _wire(checkin_app, llm_results=[turn])
    client = TestClient(checkin_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"), "I keep sinking when I try to float")

    assert response.status_code == 200
    _, params = driver.committed[0]
    assert params["outcome"] == "obstacle"
    assert params["obstacle"] == "keep sinking"


def test_checkin_intent_with_step_order_outside_the_active_plan_is_rejected(
    checkin_app, make_token
) -> None:
    """A step_order the real ContextBuilder-loaded plan doesn't contain
    (e.g. the LLM hallucinated one, or referenced a superseded plan
    generation) is rejected before any Cypher runs -- surfaces as the
    standard 500 envelope, same as any other unexpected server error."""
    intent = CompleteStepIntent(type="complete_step", step_order=7, sentiment="positive")
    turn = ChatTurn(reply="...", intents=[intent])
    _, driver, _ = _wire(checkin_app, llm_results=[turn])
    client = TestClient(checkin_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"), "done with step 7")

    assert response.status_code == 500
    assert driver.committed == []
