"""T010: route-level wizard tests using REAL LlmService/ContextBuilder/
IntentApplyService, faked only at the I/O boundary (LLM runnable, Neo4j
driver, message store) — proves the actual wiring in routes/chat.py, not
just each service in isolation (test_llm.py, test_intent_apply.py,
test_context_builder.py already cover those individually).
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from skillcoach_api.models.chat import ChatTurn
from skillcoach_api.models.intents import CreatePlanIntent, CreateSkillIntent, StepPayload
from skillcoach_api.services.context_builder import ContextBuilder
from skillcoach_api.services.intent_apply import IntentApplyService
from skillcoach_api.services.llm import LlmService
from tests.fakes import (
    FakeAnalytics,
    FakeBudget,
    FakeCadenceSchedule,
    FakeGraph,
    FakeJwksClient,
    FakeProgress,
)

pytestmark = [pytest.mark.wizard_plan, pytest.mark.chat, pytest.mark.wizard]

SESSION_ID = str(uuid.uuid4())


class FakeRunnable:
    """Captures the REAL system prompt LlmService builds, so tests assert
    on genuine prompt content (turn-count wording), not a stubbed call.
    Mimics with_structured_output(ChatTurn, include_raw=True)'s
    {raw, parsed, parsing_error} shape (005, research.md R7)."""

    def __init__(self, results: list) -> None:
        self._results = iter(results)
        self.calls: list = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        result = next(self._results)
        if isinstance(result, Exception):
            raise result
        if isinstance(result, ValidationError):
            return {"raw": None, "parsed": None, "parsing_error": result}
        return {"raw": None, "parsed": result, "parsing_error": None}


class FakeMessagesForContext:
    def __init__(self, turn_count: int, language: str = "en") -> None:
        self.turn_count = turn_count
        self.language = language
        self.inserted: list[dict] = []

    async def profile_language(self, _user_id: str) -> str:
        return self.language

    async def recent_messages(self, _session_id: str, limit: int = 20) -> list[dict]:
        return []

    async def count_user_turns(self, _session_id: str) -> int:
        return self.turn_count

    async def insert_turn(
        self, user_id, session_id, skill_id, user_text, assistant_text, modality="chat"
    ) -> None:
        self.inserted.append(
            {
                "user_id": user_id,
                "session_id": session_id,
                "skill_id": skill_id,
                "user_text": user_text,
                "assistant_text": assistant_text,
                "modality": modality,
            }
        )


class FakeSkillsForContext:
    """No existing skill — these tests exercise the wizard path only."""

    async def get_skill(self, _user_id: str, _skill_id: str):
        return None


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
def wizard_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    return create_app()


def _wire(app, *, turn_count: int, llm_results: list):
    messages = FakeMessagesForContext(turn_count=turn_count)
    driver = FakeDriver()
    runnable = FakeRunnable(llm_results)
    fakes = SimpleNamespace(
        budget=FakeBudget(),
        graph=FakeGraph(),
        messages=messages,
        context_builder=ContextBuilder(messages, FakeSkillsForContext(), FakeProgress()),
        llm=LlmService(runnable, retry_wait_multiplier=0.001),
        intent_apply=IntentApplyService(driver),
        cadence_schedule=FakeCadenceSchedule(),
        analytics=FakeAnalytics(),
    )
    app.state.services = fakes
    return fakes, driver, runnable


def _post(client, token, message="hi", new_skill_name="Swimming"):
    return client.post(
        "/v1/chat",
        json={"message": message, "session_id": SESSION_ID, "new_skill_name": new_skill_name},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_turn_below_cap_does_not_force_summarize(wizard_app, make_token) -> None:
    """user_turn_count=10 -> this is turn 11 of 12 -> not yet forced."""
    _, _, runnable = _wire(
        wizard_app, turn_count=10, llm_results=[ChatTurn(reply="ok", intents=[])]
    )
    client = TestClient(wizard_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"))

    assert response.status_code == 200
    system_prompt = runnable.calls[0][0][1]
    assert "turn 11 of a maximum 12" in system_prompt
    assert "You MUST summarize" not in system_prompt


def test_turn_at_cap_forces_summarize(wizard_app, make_token) -> None:
    """user_turn_count=11 -> this is turn 12 of 12 -> force-summarize (FR-010)."""
    _, _, runnable = _wire(
        wizard_app, turn_count=11, llm_results=[ChatTurn(reply="ok", intents=[])]
    )
    client = TestClient(wizard_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"))

    assert response.status_code == 200
    system_prompt = runnable.calls[0][0][1]
    assert "turn 12 of a maximum 12" in system_prompt
    assert "You MUST summarize" in system_prompt


def test_create_skill_and_plan_atomic_through_the_real_route(wizard_app, make_token) -> None:
    """Not FakeIntentApply — the REAL IntentApplyService running against a
    fake Neo4j driver, proving routes/chat.py's wiring genuinely produces
    one atomic transaction end to end (FR-004, SC-004)."""
    plan_intent = CreatePlanIntent(
        type="create_plan",
        skill_name="Swimming",
        goal_statement="Swim 1km",
        target_date="2026-12-01",
        weekly_days=3,
        weekly_minutes_per_day=30,
        steps=[
            StepPayload(order=i, description=f"Step {i}", cadence_per_week=3) for i in (1, 2, 3)
        ],
    )
    skill_intent = CreateSkillIntent(type="create_skill", name="Swimming")
    turn = ChatTurn(reply="Great, let's start!", intents=[skill_intent, plan_intent])
    fakes, driver, _ = _wire(wizard_app, turn_count=3, llm_results=[turn])
    client = TestClient(wizard_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"), message="yes confirm")

    assert response.status_code == 200
    body = response.json()
    assert body["skill_id"] is not None
    assert len(driver.committed) == 2
    assert "CREATE (s:Skill" in driver.committed[0][0]
    assert "CREATE (g:Goal" in driver.committed[1][0]
    assert fakes.messages.inserted[0]["skill_id"] == body["skill_id"]
    # 004: cadence_schedules kept in sync with the newly created plan.
    synced_user_id, synced_skill_id, synced_steps = fakes.cadence_schedule.synced[0]
    assert synced_user_id == "user-1"
    assert synced_skill_id == body["skill_id"]
    assert len(synced_steps) == 3


def test_checkin_intent_alone_does_not_trigger_a_cadence_sync(wizard_app, make_token) -> None:
    """A log_checkin/complete_step/report_obstacle turn never redefines a
    plan's steps -- cadence_schedule.sync must not be called for these."""
    from skillcoach_api.models.intents import CompleteStepIntent

    turn = ChatTurn(
        reply="Nice work!",
        intents=[CompleteStepIntent(type="complete_step", step_order=1, sentiment="positive")],
    )
    fakes, _, _ = _wire(wizard_app, turn_count=3, llm_results=[turn])
    client = TestClient(wizard_app, raise_server_exceptions=False)

    client.post(
        "/v1/chat",
        json={
            "message": "done",
            "session_id": SESSION_ID,
            "skill_id": str(uuid.uuid4()),
        },
        headers={"Authorization": f"Bearer {make_token(sub='user-1')}"},
    )

    assert fakes.cadence_schedule.synced == []


@pytest.mark.voice_layer
def test_modality_never_affects_llm_prompt_or_context(wizard_app, make_token) -> None:
    """003 T005 (Constitution IV): modality is stamped only on the
    persisted message row; two otherwise-identical requests differing
    only in modality must produce a byte-identical LLM prompt/context.
    Also pins that ChatRequest actually exposes `.modality` -- fails now,
    before 003's Foundational implementation, since the field doesn't
    exist yet and is silently dropped as an unrecognized extra key."""
    from skillcoach_api.models.chat import ChatRequest

    chat_req = ChatRequest.model_validate(
        {
            "message": "hi",
            "session_id": SESSION_ID,
            "new_skill_name": "Swimming",
            "modality": "chat",
        }
    )
    voice_req = ChatRequest.model_validate(
        {
            "message": "hi",
            "session_id": SESSION_ID,
            "new_skill_name": "Swimming",
            "modality": "voice",
        }
    )
    assert chat_req.modality == "chat"
    assert voice_req.modality == "voice"

    client = TestClient(wizard_app, raise_server_exceptions=False)
    token = make_token(sub="user-1")

    _, _, runnable_chat = _wire(
        wizard_app, turn_count=3, llm_results=[ChatTurn(reply="ok", intents=[])]
    )
    client.post(
        "/v1/chat",
        json=chat_req.model_dump(mode="json"),
        headers={"Authorization": f"Bearer {token}"},
    )

    _, _, runnable_voice = _wire(
        wizard_app, turn_count=3, llm_results=[ChatTurn(reply="ok", intents=[])]
    )
    client.post(
        "/v1/chat",
        json=voice_req.model_dump(mode="json"),
        headers={"Authorization": f"Bearer {token}"},
    )

    assert runnable_chat.calls == runnable_voice.calls


def test_validation_failure_exhausted_degrades_through_the_real_route(
    wizard_app, make_token
) -> None:
    """Real LlmService's feedback-retry loop exhausting -> route still
    returns 200 with a degraded reply, never a 503, and applies nothing."""

    def _bad_output() -> ValidationError:
        try:
            ChatTurn.model_validate({"reply": 1, "intents": "not-a-list"})
        except ValidationError as exc:
            return exc
        raise AssertionError("expected a ValidationError")

    _, driver, runnable = _wire(
        wizard_app, turn_count=0, llm_results=[_bad_output(), _bad_output(), _bad_output()]
    )
    client = TestClient(wizard_app, raise_server_exceptions=False)

    response = _post(client, make_token(sub="user-1"))

    assert response.status_code == 200  # not 503 — this is a validation issue, not an outage
    assert response.json()["intents"] == []
    assert driver.committed == []  # nothing applied
    assert len(runnable.calls) == 3  # 1 initial + 2 retries, per FR-006
