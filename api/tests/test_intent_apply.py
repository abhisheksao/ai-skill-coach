"""IntentApplyService: parameterized Cypher per intent, true atomicity via
execute_write (FR-004, SC-004)."""

from datetime import UTC, date, datetime

import pytest

from skillcoach_api.models.intents import (
    CompleteStepIntent,
    CreatePlanIntent,
    CreateSkillIntent,
    LogCheckinIntent,
    ReportObstacleIntent,
    ReviseGoalIntent,
    RevisePlanIntent,
    StepPayload,
)
from skillcoach_api.services.intent_apply import IntentApplyService

pytestmark = [pytest.mark.wizard_plan, pytest.mark.progress_notifications, pytest.mark.intents]

STEPS = [
    StepPayload(order=1, description="Float and glide", cadence_per_week=3),
    StepPayload(order=2, description="Kick drills", cadence_per_week=3),
    StepPayload(order=3, description="Full stroke", cadence_per_week=2),
]


class FakeTx:
    def __init__(self, fail_after: int | None) -> None:
        self.queries: list[tuple[str, dict]] = []
        self._fail_after = fail_after

    async def run(self, query: str, **params) -> None:
        self.queries.append((query, params))
        if self._fail_after is not None and len(self.queries) > self._fail_after:
            raise RuntimeError("simulated mid-transaction failure")


class FakeSession:
    def __init__(self, committed: list, fail_after: int | None) -> None:
        self._committed = committed
        self._fail_after = fail_after

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def execute_write(self, tx_func):
        tx = FakeTx(self._fail_after)
        await tx_func(tx)  # exception here means nothing gets "committed" below
        self._committed.extend(tx.queries)


class FakeDriver:
    def __init__(self, fail_after: int | None = None) -> None:
        self.committed: list[tuple[str, dict]] = []
        self._fail_after = fail_after

    def session(self) -> FakeSession:
        return FakeSession(self.committed, self._fail_after)


async def test_create_skill_alone_commits_one_parameterized_query() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    result = await service.apply_intents(
        [CreateSkillIntent(type="create_skill", name="Swimming")], "user-1"
    )

    assert len(driver.committed) == 1
    query, params = driver.committed[0]
    assert "CREATE (s:Skill" in query
    assert params["user_id"] == "user-1"
    assert params["name"] == "Swimming"
    assert "Swimming" not in query  # parameterized, never interpolated
    assert result.created_skill_id == params["skill_id"]


async def test_create_skill_and_plan_commit_atomically_together() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    intents = [
        CreateSkillIntent(type="create_skill", name="Swimming"),
        CreatePlanIntent(
            type="create_plan",
            skill_name="Swimming",
            goal_statement="Swim 1km continuously",
            target_date=date(2026, 12, 1),
            weekly_days=3,
            weekly_minutes_per_day=30,
            steps=STEPS,
        ),
    ]
    result = await service.apply_intents(intents, "user-1")

    assert len(driver.committed) == 2
    skill_query, skill_params = driver.committed[0]
    plan_query, plan_params = driver.committed[1]
    assert "CREATE (s:Skill" in skill_query
    assert "CREATE (g:Goal" in plan_query and "CREATE (p:Plan" in plan_query
    assert len(plan_params["steps"]) == 3
    assert result.created_skill_id == skill_params["skill_id"]
    # create_plan matches the skill just created IN THIS BATCH by id, not
    # by re-deriving it from the (non-unique) name (FR-012 dup names).
    assert "s:Skill {id: $skill_id}" in plan_query
    assert plan_params["skill_id"] == skill_params["skill_id"]


async def test_failure_after_first_intent_commits_nothing() -> None:
    """Atomicity: create_skill succeeding but create_plan failing must
    leave NEITHER persisted (FR-004) — this is what execute_write
    guarantees over separate auto-commit calls."""
    driver = FakeDriver(fail_after=1)  # the 2nd tx.run raises
    service = IntentApplyService(driver)
    intents = [
        CreateSkillIntent(type="create_skill", name="Swimming"),
        CreatePlanIntent(
            type="create_plan",
            skill_name="Swimming",
            goal_statement="Swim 1km",
            target_date=date(2026, 12, 1),
            weekly_days=3,
            weekly_minutes_per_day=30,
            steps=STEPS,
        ),
    ]
    with pytest.raises(RuntimeError):
        await service.apply_intents(intents, "user-1")

    assert driver.committed == []  # nothing partially written


async def test_revise_plan_supersedes_scoped_to_user_and_skill() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    await service.apply_intents(
        [RevisePlanIntent(type="revise_plan", steps=STEPS)], "user-1", skill_id="skill-1"
    )

    query, params = driver.committed[0]
    assert "SUPERSEDES" in query
    assert "WHERE NOT (old)<-[:SUPERSEDES]-(:Plan)" in query  # only the active plan
    assert "s:Skill {id: $skill_id}" in query  # by id, never by name (FR-012 dup names)
    assert params["user_id"] == "user-1"
    assert params["skill_id"] == "skill-1"


async def test_revise_plan_links_to_the_currently_active_goal_not_the_old_plans_goal() -> None:
    """Regression (004, US5/T059): _REVISE_PLAN used to follow the OLD
    plan's existing FOR_GOAL edge to find the goal to link the new plan
    to. If a revise_goal had already superseded that goal, the
    regenerated plan would silently keep pointing at the SUPERSEDED
    goal, violating FR-011's explicit requirement. Fixed to look up the
    skill's current active Goal directly, independent of whichever goal
    the old plan happened to point at."""
    driver = FakeDriver()
    service = IntentApplyService(driver)
    await service.apply_intents(
        [RevisePlanIntent(type="revise_plan", steps=STEPS)], "user-1", skill_id="skill-1"
    )

    query, _ = driver.committed[0]
    assert "MATCH (s)-[:HAS_GOAL]->(g:Goal)" in query
    assert "WHERE NOT (g)<-[:SUPERSEDES]-(:Goal)" in query
    assert "(old)-[:FOR_GOAL]->(g:Goal)" not in query


async def test_revise_plan_without_a_skill_id_raises() -> None:
    """No current-skill context = programmer error, not a silent no-op or
    a name-matching fallback that could hit the wrong skill."""
    driver = FakeDriver()
    service = IntentApplyService(driver)
    with pytest.raises(ValueError, match="skill_id"):
        await service.apply_intents([RevisePlanIntent(type="revise_plan", steps=STEPS)], "user-1")


async def test_revise_goal_supersedes_scoped_to_user_and_skill() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    await service.apply_intents(
        [
            ReviseGoalIntent(
                type="revise_goal",
                goal_statement="Swim 2km",
                target_date=date(2027, 3, 1),
            )
        ],
        "user-1",
        skill_id="skill-1",
    )

    query, params = driver.committed[0]
    assert "SUPERSEDES" in query
    assert "WHERE NOT (old)<-[:SUPERSEDES]-(:Goal)" in query  # only the active goal
    assert "s:Skill {id: $skill_id}" in query
    assert params["skill_id"] == "skill-1"
    assert params["goal_statement"] == "Swim 2km"


async def test_empty_intents_is_a_no_op() -> None:
    driver = FakeDriver()
    await IntentApplyService(driver).apply_intents([], "user-1")
    assert driver.committed == []


async def test_complete_step_creates_one_checkin_with_completed_outcome() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    result = await service.apply_intents(
        [CompleteStepIntent(type="complete_step", step_order=2, sentiment="positive")],
        "user-1",
        skill_id="skill-1",
        valid_step_orders={1, 2, 3},
        source="ui_tap",
    )

    query, params = driver.committed[0]
    assert "CREATE (c:CheckIn" in query
    assert "CREATE (c)-[:FOR_STEP]->(st)" in query
    assert params["outcome"] == "completed"
    assert params["step_order"] == 2
    assert params["sentiment"] == "positive"
    assert params["obstacle"] is None
    assert params["source"] == "ui_tap"
    assert params["skill_id"] == "skill-1"
    # ApplyResult surfaces the generated checkin_id (T053 -- the UI-native
    # POST /v1/intents/apply response needs this).
    assert result.checkin_id == params["checkin_id"]


async def test_log_checkin_creates_one_checkin_with_partial_outcome() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    await service.apply_intents(
        [
            LogCheckinIntent(
                type="log_checkin",
                step_order=1,
                outcome="partial",
                sentiment="neutral",
                obstacle="ran out of time",
            )
        ],
        "user-1",
        skill_id="skill-1",
        valid_step_orders={1, 2, 3},
    )

    _, params = driver.committed[0]
    assert params["outcome"] == "partial"
    assert params["obstacle"] == "ran out of time"
    assert params["source"] == "conversation"  # default, matches /v1/chat's caller


async def test_report_obstacle_creates_one_checkin_with_obstacle_outcome() -> None:
    driver = FakeDriver()
    service = IntentApplyService(driver)
    await service.apply_intents(
        [
            ReportObstacleIntent(
                type="report_obstacle", step_order=3, obstacle="keep sinking", sentiment="negative"
            )
        ],
        "user-1",
        skill_id="skill-1",
        valid_step_orders={1, 2, 3},
    )

    _, params = driver.committed[0]
    assert params["outcome"] == "obstacle"
    assert params["obstacle"] == "keep sinking"


async def test_checkin_without_explicit_timestamp_defaults_to_now() -> None:
    driver = FakeDriver()
    before = datetime.now(UTC)
    await IntentApplyService(driver).apply_intents(
        [CompleteStepIntent(type="complete_step", step_order=1, sentiment="positive")],
        "user-1",
        skill_id="skill-1",
        valid_step_orders={1},
    )
    after = datetime.now(UTC)

    _, params = driver.committed[0]
    written = datetime.fromisoformat(params["timestamp"])
    assert before <= written <= after


async def test_checkin_with_explicit_backdated_timestamp_is_preserved() -> None:
    """Edge Case: "I swam twice over the weekend" -- the intent may carry a
    past timestamp, recorded verbatim rather than "now" (data-model.md)."""
    driver = FakeDriver()
    backdated = datetime(2026, 7, 10, 9, 0, tzinfo=UTC)
    await IntentApplyService(driver).apply_intents(
        [
            LogCheckinIntent(
                type="log_checkin",
                step_order=1,
                outcome="partial",
                sentiment="positive",
                timestamp=backdated,
            )
        ],
        "user-1",
        skill_id="skill-1",
        valid_step_orders={1},
    )

    _, params = driver.committed[0]
    assert params["timestamp"] == backdated.isoformat()


async def test_checkin_intent_without_skill_id_raises() -> None:
    driver = FakeDriver()
    with pytest.raises(ValueError, match="skill_id"):
        await IntentApplyService(driver).apply_intents(
            [CompleteStepIntent(type="complete_step", step_order=1, sentiment="positive")],
            "user-1",
        )


async def test_checkin_intent_with_step_order_outside_active_plan_raises() -> None:
    """A step_order the caller's already-loaded plan doesn't contain -- e.g.
    a stale client referencing a step from a superseded plan generation --
    fails fast in Python, no Cypher runs at all (T003)."""
    driver = FakeDriver()
    with pytest.raises(ValueError, match="step_order 9"):
        await IntentApplyService(driver).apply_intents(
            [CompleteStepIntent(type="complete_step", step_order=9, sentiment="positive")],
            "user-1",
            skill_id="skill-1",
            valid_step_orders={1, 2, 3},
        )
    assert driver.committed == []
