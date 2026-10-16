"""SessionSummaryService: the eligibility filter itself (inactivity
cutoff, `skill_id IS NULL` exclusion) lives in the `eligible_sessions_for_
summary` SQL RPC (migration) — same Postgres-fan-out/Neo4j-decision
division of labor as the notifications scan (research.md R1/R2), so
this file proves the SERVICE's contract with that RPC (the cutoff it
passes, what it does with the candidates), not the SQL itself. Also
covers failure isolation (FR-006 scenario 3): one session's summarization
failing must not block any other."""

from datetime import UTC, datetime, timedelta

import pytest

from skillcoach_api import constants
from skillcoach_api.services.session_summary import SessionSummaryService
from tests.fakes import FakeAnalytics

pytestmark = [pytest.mark.progress_notifications, pytest.mark.sessions]


class FakeRest:
    def __init__(self, candidates: list[dict] | None = None, messages_by_session=None) -> None:
        self.rpc_calls: list[tuple] = []
        self._candidates = candidates or []
        self._messages_by_session = messages_by_session or {}

    async def rpc(self, function: str, payload: dict):
        self.rpc_calls.append((function, payload))
        return self._candidates

    async def select_many(self, table, filters, columns, order=None, limit=None, raw_filters=None):
        if table == "messages":
            return self._messages_by_session.get(filters["session_id"], [])
        return []


class FakeResult:
    def __init__(self, found: bool) -> None:
        self._found = found

    async def single(self):
        return {"sess": "x"} if self._found else None


class FakeSession:
    def __init__(self, existing_session_ids: set[str], committed: list) -> None:
        self._existing = existing_session_ids
        self._committed = committed

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def run(self, query: str, **params):
        if "RETURN sess LIMIT 1" in query:
            return FakeResult(params["session_id"] in self._existing)
        self._committed.append((query, params))
        return None


class FakeDriver:
    def __init__(self, existing_session_ids: set[str] | None = None) -> None:
        self.committed: list = []
        self._existing = existing_session_ids or set()

    def session(self) -> FakeSession:
        return FakeSession(self._existing, self.committed)


class FakeBudget:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self.reports: list[tuple[str, dict | None]] = []

    async def acquire(self, user_id: str) -> None:
        self.calls.append(user_id)

    async def report(self, user_id: str, usage_metadata: dict | None) -> None:
        self.reports.append((user_id, usage_metadata))


class FakeLlm:
    def __init__(self, summary: str = "Summary text", fail_on_call: int | None = None) -> None:
        self.summary = summary
        self.fail_on_call = fail_on_call
        self.calls: list[str] = []

    async def generate_session_summary(self, transcript: str):
        self.calls.append(transcript)
        if self.fail_on_call is not None and len(self.calls) == self.fail_on_call:
            raise RuntimeError("provider outage")
        return self.summary, None


def make_candidate(
    user_id: str = "user-1", skill_id: str = "skill-1", session_id: str = "session-1"
) -> dict:
    now = datetime.now(UTC)
    return {
        "user_id": user_id,
        "skill_id": skill_id,
        "session_id": session_id,
        "started_at": (now - timedelta(minutes=40)).isoformat(),
        "ended_at": (now - timedelta(minutes=35)).isoformat(),
    }


async def test_eligible_session_gets_summarized_and_written() -> None:
    rest = FakeRest(
        candidates=[make_candidate()],
        messages_by_session={
            "session-1": [
                {"sender": "user", "content": "hi"},
                {"sender": "assistant", "content": "hello"},
            ]
        },
    )
    driver = FakeDriver()
    budget = FakeBudget()
    llm = FakeLlm(summary="Talked about drills.")
    service = SessionSummaryService(rest, driver, budget, llm, FakeAnalytics())

    count = await service.summarize_eligible_sessions()

    assert count == 1
    assert budget.calls == ["user-1"]
    assert len(driver.committed) == 1
    query, params = driver.committed[0]
    assert "CREATE (sess:Session" in query
    assert params["summary"] == "Talked about drills."
    assert params["session_id"] == "session-1"


async def test_session_ended_emitted_with_skill_id_and_message_count() -> None:
    rest = FakeRest(
        candidates=[make_candidate(user_id="user-1", skill_id="skill-1", session_id="session-1")],
        messages_by_session={
            "session-1": [
                {"sender": "user", "content": "hi"},
                {"sender": "assistant", "content": "hello"},
                {"sender": "user", "content": "bye"},
            ]
        },
    )
    analytics = FakeAnalytics()
    service = SessionSummaryService(rest, FakeDriver(), FakeBudget(), FakeLlm(), analytics)

    await service.summarize_eligible_sessions()

    assert ("session_ended", "user-1", {"skill_id": "skill-1", "message_count": 3}) in (
        analytics.emitted
    )


async def test_analytics_failure_never_blocks_summarization() -> None:
    """005, plan.md note 5: fire-and-forget -- a real AnalyticsService
    wired to an always-failing insert must not stop the Session node
    from being written."""
    from coach_core.analytics import AnalyticsService

    class FailingInsertRest(FakeRest):
        async def insert(self, table: str, rows: list[dict]) -> None:
            raise RuntimeError("PostgREST unreachable")

    rest = FailingInsertRest(
        candidates=[make_candidate(session_id="session-1")],
        messages_by_session={"session-1": [{"sender": "user", "content": "hi"}]},
    )
    driver = FakeDriver()
    service = SessionSummaryService(
        rest, driver, FakeBudget(), FakeLlm(), AnalyticsService(rest)
    )

    count = await service.summarize_eligible_sessions()

    assert count == 1
    assert len(driver.committed) == 1


async def test_session_with_an_existing_session_node_is_skipped() -> None:
    rest = FakeRest(
        candidates=[make_candidate(session_id="session-1")],
        messages_by_session={"session-1": [{"sender": "user", "content": "hi"}]},
    )
    driver = FakeDriver(existing_session_ids={"session-1"})
    service = SessionSummaryService(rest, driver, FakeBudget(), FakeLlm(), FakeAnalytics())

    count = await service.summarize_eligible_sessions()

    assert count == 0
    assert driver.committed == []


async def test_session_with_no_messages_is_skipped() -> None:
    rest = FakeRest(candidates=[make_candidate(session_id="session-1")], messages_by_session={})
    service = SessionSummaryService(rest, FakeDriver(), FakeBudget(), FakeLlm(), FakeAnalytics())

    count = await service.summarize_eligible_sessions()

    assert count == 0


async def test_a_failing_summarization_is_logged_and_does_not_block_other_sessions() -> None:
    """FR-006 scenario 3."""
    rest = FakeRest(
        candidates=[make_candidate(session_id="session-1"), make_candidate(session_id="session-2")],
        messages_by_session={
            "session-1": [{"sender": "user", "content": "hi"}],
            "session-2": [{"sender": "user", "content": "hey"}],
        },
    )
    driver = FakeDriver()
    llm = FakeLlm(fail_on_call=1)  # session-1's summarize call fails
    service = SessionSummaryService(rest, driver, FakeBudget(), llm, FakeAnalytics())

    count = await service.summarize_eligible_sessions()

    assert count == 1  # session-2 still succeeded despite session-1 failing
    assert len(driver.committed) == 1
    _, params = driver.committed[0]
    assert params["session_id"] == "session-2"


async def test_cutoff_passed_to_the_rpc_matches_the_inactivity_threshold() -> None:
    rest = FakeRest(candidates=[])
    service = SessionSummaryService(rest, FakeDriver(), FakeBudget(), FakeLlm(), FakeAnalytics())

    before = datetime.now(UTC)
    await service.summarize_eligible_sessions()
    after = datetime.now(UTC)

    _, payload = rest.rpc_calls[0]
    cutoff = datetime.fromisoformat(payload["cutoff"])
    expected_min = before - timedelta(minutes=constants.SESSION_INACTIVITY_MINUTES)
    expected_max = after - timedelta(minutes=constants.SESSION_INACTIVITY_MINUTES)
    assert expected_min <= cutoff <= expected_max
