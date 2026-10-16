"""ContextBuilder: assembles profile language + active-skill subgraph (if
any) + recent messages + turn count (FR-008), and — 004 — a gap
description when the active skill has a behind-cadence step. Named a
non-negotiable unit-test target by Constitution VIII, so this file also
covers its negative paths explicitly: a missing/not-owned skill, and a
provider failure propagating rather than being silently swallowed."""

from datetime import UTC, date, datetime, timedelta

import pytest

from skillcoach_api import constants
from skillcoach_api.models.skills import GoalDetail, PlanDetail, SkillDetail, StepDetail
from skillcoach_api.services.context_builder import ContextBuilder
from skillcoach_api.services.progress import SkillProgress, StepProgress

pytestmark = [pytest.mark.wizard_plan, pytest.mark.progress_notifications, pytest.mark.context]


class FakeMessages:
    def __init__(
        self, language: str, recent: list[dict], turn_count: int, timezone: str = "UTC"
    ) -> None:
        self.language = language
        self.recent = recent
        self.turn_count = turn_count
        self.timezone = timezone
        self.calls: list[tuple] = []

    async def profile_language(self, user_id: str) -> str:
        self.calls.append(("profile_language", user_id))
        return self.language

    async def profile_timezone(self, user_id: str) -> str:
        self.calls.append(("profile_timezone", user_id))
        return self.timezone

    async def recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        self.calls.append(("recent_messages", session_id))
        return self.recent

    async def count_user_turns(self, session_id: str) -> int:
        self.calls.append(("count_user_turns", session_id))
        return self.turn_count


class FakeSkills:
    def __init__(
        self,
        detail: SkillDetail | None,
        summaries: list[str] | None = None,
        goal_history: list | None = None,
    ) -> None:
        self.detail = detail
        self.summaries = summaries or []
        self.goal_history_value = goal_history or []
        self.calls: list[tuple] = []
        self.summary_calls: list[tuple] = []
        self.goal_history_calls: list[tuple] = []

    async def get_skill(self, user_id: str, skill_id: str) -> SkillDetail | None:
        self.calls.append((user_id, skill_id))
        return self.detail

    async def recent_session_summaries(self, user_id: str, skill_id: str, limit: int) -> list[str]:
        self.summary_calls.append((user_id, skill_id, limit))
        return self.summaries

    async def goal_revision_history(self, user_id: str, skill_id: str) -> list:
        self.goal_history_calls.append((user_id, skill_id))
        return self.goal_history_value


class FakeProgress:
    """Not-behind by default; tests opt into a specific SkillProgress."""

    def __init__(self, progress: SkillProgress | None = None) -> None:
        self._progress = progress
        self.calls: list[tuple] = []

    async def compute(self, user_id: str, skill_id: str, timezone: str) -> SkillProgress:
        self.calls.append((user_id, skill_id, timezone))
        return self._progress or SkillProgress(
            skill_id=skill_id, completed_steps=[], total_steps=0, streak_days=0, steps=[]
        )


SKILL = SkillDetail(
    id="skill-1",
    name="Swimming",
    goal=GoalDetail(statement="Swim 1km", target_date=date(2026, 12, 1)),
    plan=PlanDetail(
        id="plan-1",
        generation=0,
        steps=[StepDetail(order=1, description="Float", cadence_per_week=3)],
    ),
)


async def test_build_without_skill_id_skips_skill_lookup() -> None:
    messages = FakeMessages("hi", recent=[{"sender": "user", "content": "hello"}], turn_count=1)
    skills = FakeSkills(SKILL)
    progress = FakeProgress()
    context = await ContextBuilder(messages, skills, progress).build("user-1", None, "session-1")

    assert context.skill is None
    assert skills.calls == []  # never queried when skill_id is None
    assert progress.calls == []  # no skill -- nothing to check cadence against
    assert context.language == "hi"
    assert context.user_turn_count == 1
    assert context.recent_messages == [{"sender": "user", "content": "hello"}]
    assert context.gap_description is None


async def test_build_with_skill_id_includes_subgraph() -> None:
    messages = FakeMessages("en", recent=[], turn_count=3)
    skills = FakeSkills(SKILL)
    context = await ContextBuilder(messages, skills, FakeProgress()).build(
        "user-1", "skill-1", "session-1"
    )

    assert context.skill is SKILL
    assert skills.calls == [("user-1", "skill-1")]


async def test_build_scopes_all_lookups_to_the_given_session() -> None:
    messages = FakeMessages("en", recent=[], turn_count=0)
    await ContextBuilder(messages, FakeSkills(None), FakeProgress()).build(
        "user-1", None, "session-42"
    )

    assert ("recent_messages", "session-42") in messages.calls
    assert ("count_user_turns", "session-42") in messages.calls


async def test_build_with_missing_or_not_owned_skill_returns_none_without_crashing() -> None:
    messages = FakeMessages("en", recent=[], turn_count=0)
    skills = FakeSkills(None)  # skill_id given, but not found/not owned
    context = await ContextBuilder(messages, skills, FakeProgress()).build(
        "user-1", "skill-x", "session-1"
    )

    assert context.skill is None
    assert skills.calls == [("user-1", "skill-x")]


async def test_build_with_an_active_skill_includes_recent_session_summaries() -> None:
    messages = FakeMessages("en", recent=[], turn_count=3)
    skills = FakeSkills(SKILL, summaries=["Last time: struggled with flip turns.", "Great week!"])
    context = await ContextBuilder(messages, skills, FakeProgress()).build(
        "user-1", "skill-1", "session-1"
    )

    assert context.recent_session_summaries == [
        "Last time: struggled with flip turns.",
        "Great week!",
    ]
    assert skills.summary_calls == [("user-1", "skill-1", constants.SESSION_SUMMARY_COUNT)]


async def test_build_without_skill_id_has_no_session_summaries() -> None:
    messages = FakeMessages("en", recent=[], turn_count=0)
    skills = FakeSkills(None, summaries=["should never be returned"])
    context = await ContextBuilder(messages, skills, FakeProgress()).build(
        "user-1", None, "session-1"
    )

    assert context.recent_session_summaries == []
    assert skills.summary_calls == []


async def test_build_with_an_active_skill_includes_goal_revision_history() -> None:
    """T060/SC-005: after two goal revisions, all three goals are
    retrievable in order via the context."""
    history = [
        GoalDetail(statement="Swim 1km", target_date=date(2026, 10, 1)),
        GoalDetail(statement="Swim 2km", target_date=date(2026, 11, 1)),
        GoalDetail(statement="Swim a 5k open water race", target_date=date(2027, 1, 1)),
    ]
    messages = FakeMessages("en", recent=[], turn_count=3)
    skills = FakeSkills(SKILL, goal_history=history)
    context = await ContextBuilder(messages, skills, FakeProgress()).build(
        "user-1", "skill-1", "session-1"
    )

    assert context.goal_history == history
    assert [g.statement for g in context.goal_history] == [
        "Swim 1km",
        "Swim 2km",
        "Swim a 5k open water race",
    ]
    assert skills.goal_history_calls == [("user-1", "skill-1")]


async def test_build_without_skill_id_has_no_goal_history() -> None:
    messages = FakeMessages("en", recent=[], turn_count=0)
    skills = FakeSkills(
        None, goal_history=[GoalDetail(statement="x", target_date=date(2026, 1, 1))]
    )
    context = await ContextBuilder(messages, skills, FakeProgress()).build(
        "user-1", None, "session-1"
    )

    assert context.goal_history == []
    assert skills.goal_history_calls == []


async def test_build_with_a_behind_cadence_step_includes_a_gap_description() -> None:
    messages = FakeMessages("en", recent=[], turn_count=3, timezone="America/Los_Angeles")
    skills = FakeSkills(SKILL)
    now = datetime.now(UTC)
    progress = FakeProgress(
        SkillProgress(
            skill_id="skill-1",
            completed_steps=[],
            total_steps=1,
            streak_days=0,
            steps=[
                StepProgress(
                    order=1,
                    completed=False,
                    behind_cadence=True,
                    last_checkin_at=now - timedelta(days=5),
                    anchor_at=now - timedelta(days=5),
                )
            ],
        )
    )
    context = await ContextBuilder(messages, skills, progress).build(
        "user-1", "skill-1", "session-1"
    )

    assert context.gap_description is not None
    assert "Float" in context.gap_description  # the step's own description
    assert "5" in context.gap_description  # days since
    assert progress.calls == [("user-1", "skill-1", "America/Los_Angeles")]


async def test_build_with_no_behind_cadence_step_has_no_gap_description() -> None:
    messages = FakeMessages("en", recent=[], turn_count=3)
    skills = FakeSkills(SKILL)
    progress = FakeProgress(
        SkillProgress(
            skill_id="skill-1",
            completed_steps=[],
            total_steps=1,
            streak_days=2,
            steps=[
                StepProgress(
                    order=1,
                    completed=False,
                    behind_cadence=False,
                    last_checkin_at=datetime.now(UTC),
                    anchor_at=datetime.now(UTC),
                )
            ],
        )
    )
    context = await ContextBuilder(messages, skills, progress).build(
        "user-1", "skill-1", "session-1"
    )

    assert context.gap_description is None


class FailingMessages:
    async def profile_language(self, user_id: str) -> str:
        raise RuntimeError("supabase down")

    async def recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        raise RuntimeError("supabase down")

    async def count_user_turns(self, session_id: str) -> int:
        raise RuntimeError("supabase down")


async def test_build_propagates_a_provider_failure_rather_than_swallowing_it() -> None:
    """ContextBuilder.build has no try/except -- this documents the current
    fail-open-to-the-caller behavior explicitly, since Constitution VIII
    names this file as a non-negotiable unit-test target."""
    with pytest.raises(RuntimeError, match="supabase down"):
        await ContextBuilder(FailingMessages(), FakeSkills(None), FakeProgress()).build(
            "user-1", None, "session-1"
        )
