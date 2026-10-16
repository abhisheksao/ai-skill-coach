"""T020: skill-level isolation — extends 001's test_tenancy.py pattern
(user-level scoping) to skill-level scoping within the SAME user.

Deliberately exercises the hard case: two skills sharing the same name
(FR-012 permits this — the duplicate warning can be dismissed). This is
exactly the scenario that exposed a real bug during Phase 4: revise_plan/
revise_goal originally matched a skill by name, which is ambiguous once
two skills share one. Fixed in intent_apply.py to match by id, supplied
by the caller's already-resolved skill_id — never re-derived from a name
the LLM might echo. These tests prove that fix through the real route.
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from skillcoach_api.models.chat import ChatTurn
from skillcoach_api.models.intents import ReviseGoalIntent
from skillcoach_api.services.context_builder import ContextBuilder
from skillcoach_api.services.intent_apply import IntentApplyService
from tests.fakes import FakeAnalytics, FakeBudget, FakeGraph, FakeJwksClient, FakeProgress

pytestmark = [pytest.mark.wizard_plan, pytest.mark.skills, pytest.mark.tenancy]

SESSION_ID = str(uuid.uuid4())
SKILL_A = "aaaaaaaa-0000-0000-0000-000000000001"
SKILL_B = "bbbbbbbb-0000-0000-0000-000000000002"


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


class FakeRunnable:
    def __init__(self, turn: ChatTurn) -> None:
        self._turn = turn
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        return self._turn


class FakeMessages:
    """Both skills named "Swimming" -- the ambiguous case. Tracks every
    inserted row so tests can assert skill B is never touched."""

    def __init__(self) -> None:
        self.inserted: list[dict] = []

    async def profile_language(self, _user_id: str) -> str:
        return "en"

    async def profile_timezone(self, _user_id: str) -> str:
        return "UTC"

    async def recent_messages(self, _session_id: str, limit: int = 20) -> list[dict]:
        return []

    async def count_user_turns(self, _session_id: str) -> int:
        return 1

    async def insert_turn(
        self, user_id, session_id, skill_id, user_text, assistant_text, modality="chat"
    ) -> None:
        self.inserted.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "skill_id": skill_id,
                "modality": modality,
            }
        )


class FakeSkillsSameName:
    """Both SKILL_A and SKILL_B are named "Swimming" -- get_skill returns
    the detail matching the REQUESTED id, proving lookups never conflate
    the two just because names collide."""

    async def recent_session_summaries(self, _user_id: str, _skill_id: str, _limit: int):
        return []

    async def goal_revision_history(self, _user_id: str, _skill_id: str):
        return []

    async def get_skill(self, _user_id: str, skill_id: str):
        from datetime import date

        from skillcoach_api.models.skills import GoalDetail, PlanDetail, SkillDetail, StepDetail

        if skill_id not in (SKILL_A, SKILL_B):
            return None
        return SkillDetail(
            id=skill_id,
            name="Swimming",  # SAME name for both -- the hard case
            goal=GoalDetail(statement=f"Goal for {skill_id}", target_date=date(2026, 12, 1)),
            plan=PlanDetail(
                id=f"plan-{skill_id}",
                generation=0,
                steps=[StepDetail(order=1, description="Float", cadence_per_week=3)],
            ),
        )


@pytest.fixture
def isolation_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    return create_app()


def _wire(app, *, revise_turn: ChatTurn):
    messages = FakeMessages()
    driver = FakeDriver()
    runnable = FakeRunnable(revise_turn)
    services = SimpleNamespace(
        budget=FakeBudget(),
        graph=FakeGraph(),
        messages=messages,
        context_builder=ContextBuilder(messages, FakeSkillsSameName(), FakeProgress()),
        llm=_LlmAdapter(runnable),
        intent_apply=IntentApplyService(driver),
        analytics=FakeAnalytics(),
    )
    app.state.services = services
    return services, driver, messages


class _LlmAdapter:
    """Route only calls generate_coaching_turn for an existing skill_id;
    adapt the simple FakeRunnable to that one method."""

    def __init__(self, runnable: FakeRunnable) -> None:
        self._runnable = runnable

    async def generate_coaching_turn(self, _message: str, _context):
        turn = await self._runnable.ainvoke([])
        return turn, None


def _post_chat(client, token, skill_id: str, message: str = "let's change my goal"):
    return client.post(
        "/v1/chat",
        json={"message": message, "session_id": SESSION_ID, "skill_id": skill_id},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_revise_goal_on_skill_a_never_touches_skill_b_despite_same_name(
    isolation_app, make_token
) -> None:
    revise_turn = ChatTurn(
        reply="Updated your goal!",
        intents=[
            ReviseGoalIntent(
                type="revise_goal", goal_statement="Swim 2km", target_date="2027-03-01"
            )
        ],
    )
    _, driver, messages = _wire(isolation_app, revise_turn=revise_turn)
    client = TestClient(isolation_app, raise_server_exceptions=False)

    response = _post_chat(client, make_token(sub="user-1"), skill_id=SKILL_A)

    assert response.status_code == 200
    assert len(driver.committed) == 1
    query, params = driver.committed[0]
    assert "s:Skill {id: $skill_id}" in query  # matched by id, not the shared name
    assert params["skill_id"] == SKILL_A
    assert params["skill_id"] != SKILL_B

    # message rows carry skill A's id, never skill B's
    assert all(row["skill_id"] == SKILL_A for row in messages.inserted)


def test_conversation_on_skill_b_is_symmetric(isolation_app, make_token) -> None:
    """Same scenario, reversed target -- proves this isn't an artifact of
    SKILL_A happening to be scoped correctly by coincidence."""
    revise_turn = ChatTurn(
        reply="Updated your goal!",
        intents=[
            ReviseGoalIntent(
                type="revise_goal", goal_statement="Swim 3km", target_date="2027-06-01"
            )
        ],
    )
    _, driver, messages = _wire(isolation_app, revise_turn=revise_turn)
    client = TestClient(isolation_app, raise_server_exceptions=False)

    response = _post_chat(client, make_token(sub="user-1"), skill_id=SKILL_B)

    assert response.status_code == 200
    _, params = driver.committed[0]
    assert params["skill_id"] == SKILL_B
    assert all(row["skill_id"] == SKILL_B for row in messages.inserted)


async def test_context_builder_disambiguates_same_named_skills_by_id(isolation_app) -> None:
    """Belt-and-suspenders: the context assembled for skill A must reflect
    skill A's own goal, never skill B's, even though the only
    differentiator between them is the id -- their names are identical."""
    services, _, _ = _wire(isolation_app, revise_turn=ChatTurn(reply="ok", intents=[]))

    context_a = await services.context_builder.build("user-1", SKILL_A, SESSION_ID)
    context_b = await services.context_builder.build("user-1", SKILL_B, SESSION_ID)

    assert context_a.skill.id == SKILL_A
    assert context_a.skill.goal.statement == f"Goal for {SKILL_A}"
    assert context_b.skill.id == SKILL_B
    assert context_b.skill.goal.statement == f"Goal for {SKILL_B}"
    assert context_a.skill.goal.statement != context_b.skill.goal.statement
