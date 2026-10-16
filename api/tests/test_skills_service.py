"""SkillsService: read queries scoped to user_id, generation derivation, and
a simulated Aura/Neo4j outage propagating rather than being swallowed --
this is where the "simulated graph outage" quickstart scenario actually
gets its automated coverage, at the unit level."""

from datetime import date, datetime

import pytest

from skillcoach_api.services.skills import SkillsService

pytestmark = [pytest.mark.wizard_plan, pytest.mark.skills]


class FakeResult:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record

    async def single(self) -> dict | None:
        return self._records[0] if self._records else None


class FakeSession:
    def __init__(self, records: list[dict], captured: list) -> None:
        self._records = records
        self._captured = captured

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def run(self, query: str, **params):
        self._captured.append((query, params))
        return FakeResult(self._records)


class FakeDriver:
    def __init__(self, records: list[dict]) -> None:
        self.captured: list = []
        self._records = records

    def session(self) -> FakeSession:
        return FakeSession(self._records, self.captured)


async def test_list_skills_maps_rows_and_scopes_to_user() -> None:
    driver = FakeDriver(
        [
            {
                "id": "skill-1",
                "name": "Swimming",
                "created_at": datetime(2026, 7, 14, 9, 0),
                "goal_statement": "Swim 1km",
                "target_date": date(2026, 12, 1),
                "step_count": 4,
            }
        ]
    )
    skills = await SkillsService(driver).list_skills("user-1")

    assert len(skills) == 1
    assert skills[0].name == "Swimming"
    assert skills[0].step_count == 4
    _, params = driver.captured[0]
    assert params == {"user_id": "user-1"}


async def test_get_skill_returns_none_when_not_found() -> None:
    detail = await SkillsService(FakeDriver([])).get_skill("user-1", "missing-skill")
    assert detail is None


async def test_get_skill_maps_ordered_steps_and_generation() -> None:
    driver = FakeDriver(
        [
            {
                "id": "skill-1",
                "name": "Swimming",
                "goal_statement": "Swim 1km",
                "target_date": date(2026, 12, 1),
                "plan_id": "plan-2",
                "generation": 2,
                "steps": [
                    {"order": 1, "description": "Float and glide", "cadence_per_week": 3},
                    {"order": 2, "description": "Kick drills", "cadence_per_week": 3},
                ],
            }
        ]
    )
    detail = await SkillsService(driver).get_skill("user-1", "skill-1")

    assert detail is not None
    assert detail.plan.generation == 2
    assert [s.order for s in detail.plan.steps] == [1, 2]
    _, params = driver.captured[0]
    assert params == {"user_id": "user-1", "skill_id": "skill-1"}


class FailingSession:
    async def __aenter__(self) -> "FailingSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def run(self, query: str, **params):
        raise RuntimeError("aura paused")


class FailingDriver:
    def session(self) -> FailingSession:
        return FailingSession()


async def test_list_skills_propagates_a_graph_failure() -> None:
    with pytest.raises(RuntimeError, match="aura paused"):
        await SkillsService(FailingDriver()).list_skills("user-1")


async def test_get_skill_propagates_a_graph_failure() -> None:
    with pytest.raises(RuntimeError, match="aura paused"):
        await SkillsService(FailingDriver()).get_skill("user-1", "skill-1")


async def test_recent_session_summaries_maps_rows_most_recent_first() -> None:
    driver = FakeDriver(
        [
            {"summary": "Struggled with flip turns.", "ended_at": datetime(2026, 7, 16, 20, 0)},
            {
                "summary": "Great progress on float drills.",
                "ended_at": datetime(2026, 7, 10, 20, 0),
            },
        ]
    )
    summaries = await SkillsService(driver).recent_session_summaries("user-1", "skill-1", limit=5)

    assert summaries == ["Struggled with flip turns.", "Great progress on float drills."]
    _, params = driver.captured[0]
    assert params == {"user_id": "user-1", "skill_id": "skill-1", "limit": 5}


async def test_recent_session_summaries_propagates_a_graph_failure() -> None:
    with pytest.raises(RuntimeError, match="aura paused"):
        await SkillsService(FailingDriver()).recent_session_summaries("user-1", "skill-1", limit=5)


async def test_goal_revision_history_returns_all_goals_oldest_first() -> None:
    """T060/SC-005: after revisions, all goals in the SUPERSEDES chain
    are retrievable in chronological order -- the current active goal is
    always last."""
    driver = FakeDriver(
        [
            {
                "statement": "Swim 1km",
                "target_date": date(2026, 10, 1),
                "created_at": datetime(2026, 1, 1),
            },
            {
                "statement": "Swim 2km",
                "target_date": date(2026, 11, 1),
                "created_at": datetime(2026, 3, 1),
            },
            {
                "statement": "Swim a 5k open water race",
                "target_date": date(2027, 1, 1),
                "created_at": datetime(2026, 6, 1),
            },
        ]
    )
    history = await SkillsService(driver).goal_revision_history("user-1", "skill-1")

    assert [g.statement for g in history] == ["Swim 1km", "Swim 2km", "Swim a 5k open water race"]
    assert history[-1].statement == "Swim a 5k open water race"  # current goal last
    _, params = driver.captured[0]
    assert params == {"user_id": "user-1", "skill_id": "skill-1"}


async def test_goal_revision_history_with_no_revisions_returns_just_the_current_goal() -> None:
    driver = FakeDriver(
        [
            {
                "statement": "Swim 1km",
                "target_date": date(2026, 12, 1),
                "created_at": datetime(2026, 1, 1),
            }
        ]
    )
    history = await SkillsService(driver).goal_revision_history("user-1", "skill-1")

    assert len(history) == 1


async def test_goal_revision_history_propagates_a_graph_failure() -> None:
    with pytest.raises(RuntimeError, match="aura paused"):
        await SkillsService(FailingDriver()).goal_revision_history("user-1", "skill-1")
