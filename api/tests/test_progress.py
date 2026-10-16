"""ProgressService: streak/cadence-adherence/completed-steps math against
hand-computed fixtures (SC-002) -- every value must be provably derivable
from CheckIn records alone, with no stored counter anywhere."""

from datetime import UTC, datetime, timedelta

import pytest

from skillcoach_api import constants
from skillcoach_api.services.progress import ProgressService

pytestmark = [pytest.mark.progress_notifications, pytest.mark.progress]


class FakeResult:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for record in self._records:
            yield record


class FakeSession:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def run(self, query: str, **params):
        return FakeResult(self._records)


class FakeDriver:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def session(self) -> FakeSession:
        return FakeSession(self._records)


def step_record(
    order: int,
    cadence_per_week: int,
    checkins: list[dict],
    plan_created_at: datetime,
) -> dict:
    return {
        "step_order": order,
        "cadence_per_week": cadence_per_week,
        "checkins": checkins,
        "plan_created_at": plan_created_at,
    }


def checkin(outcome: str, timestamp: datetime) -> dict:
    return {"outcome": outcome, "timestamp": timestamp}


async def test_completed_steps_and_total_steps() -> None:
    now = datetime.now(UTC)
    driver = FakeDriver(
        [
            step_record(
                1, 3, [checkin("completed", now - timedelta(days=1))], now - timedelta(days=30)
            ),
            step_record(
                2, 7, [checkin("partial", now - timedelta(days=1))], now - timedelta(days=30)
            ),
        ]
    )
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.completed_steps == [1]
    assert progress.total_steps == 2
    assert [s.completed for s in progress.steps] == [True, False]


async def test_step_with_no_checkins_is_not_completed_and_behind_after_plan_created() -> None:
    now = datetime.now(UTC)
    plan_created = now - timedelta(days=30)
    driver = FakeDriver([step_record(1, 7, [], plan_created)])
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.completed_steps == []
    assert progress.steps[0].last_checkin_at is None
    assert progress.steps[0].behind_cadence is True  # 30 days since plan creation, never checked in
    assert progress.steps[0].anchor_at == plan_created  # falls back to plan creation, not "now"
    assert progress.streak_days == 0


async def test_step_with_a_checkin_uses_it_as_the_anchor_not_plan_created_at() -> None:
    now = datetime.now(UTC)
    recent = now - timedelta(hours=2)
    driver = FakeDriver([step_record(1, 7, [checkin("partial", recent)], now - timedelta(days=30))])
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.steps[0].anchor_at == recent


async def test_same_day_duplicate_checkins_count_once_toward_streak() -> None:
    """Edge Case: multiple check-ins for the same step on the same day are
    all recorded, but the streak must not double-count that day."""
    now = datetime.now(UTC)
    driver = FakeDriver(
        [
            step_record(
                1,
                7,
                [checkin("partial", now), checkin("partial", now - timedelta(hours=6))],
                now - timedelta(days=10),
            )
        ]
    )
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.streak_days == 1


async def test_broken_then_resumed_streak_only_counts_the_current_run() -> None:
    now = datetime.now(UTC)
    driver = FakeDriver(
        [
            step_record(
                1,
                7,
                [
                    checkin("partial", now),
                    checkin("partial", now - timedelta(days=1)),
                    checkin("partial", now - timedelta(days=2)),
                    # Gap here -- day 3/4 missing -- then an isolated older check-in.
                    checkin("partial", now - timedelta(days=10)),
                ],
                now - timedelta(days=30),
            )
        ]
    )
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.streak_days == 3  # only today/yesterday/day-before, not the day-10 outlier


async def test_streak_is_zero_when_most_recent_checkin_is_older_than_yesterday() -> None:
    now = datetime.now(UTC)
    driver = FakeDriver(
        [step_record(1, 7, [checkin("partial", now - timedelta(days=3))], now - timedelta(days=30))]
    )
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.streak_days == 0


async def test_behind_cadence_boundary_is_inclusive_of_the_exact_multiplier() -> None:
    """Boundary case at exactly CADENCE_BEHIND_MULTIPLIER x expected_interval
    (cadence_per_week=7 -> expected_interval=1 day). A small buffer offsets
    wall-clock drift between building the fixture and the service's own
    `datetime.now()` call a moment later -- without it this test would be
    flaky, not because the boundary logic is wrong."""
    now = datetime.now(UTC)
    threshold = timedelta(days=constants.CADENCE_BEHIND_MULTIPLIER * (7 / 7))

    at_boundary = FakeDriver(
        [
            step_record(
                1,
                7,
                [checkin("partial", now - threshold + timedelta(milliseconds=500))],
                now - timedelta(days=30),
            )
        ]
    )
    progress = await ProgressService(at_boundary).compute("user-1", "skill-1", "UTC")
    assert progress.steps[0].behind_cadence is False

    just_past = FakeDriver(
        [
            step_record(
                1,
                7,
                [checkin("partial", now - threshold - timedelta(seconds=1))],
                now - timedelta(days=30),
            )
        ]
    )
    progress = await ProgressService(just_past).compute("user-1", "skill-1", "UTC")
    assert progress.steps[0].behind_cadence is True


async def test_uses_checkin_timestamp_not_created_at_for_streak_and_cadence() -> None:
    """Edge Case: "I swam twice over the weekend" -- a CheckIn's `timestamp`
    may be days before its `created_at` (when the row was actually
    written); streak/cadence math keys off `timestamp` only (data-model.md
    distinguishes the two properties explicitly) -- this service's query
    never even reads `created_at`, so this is a structural guarantee, not
    just a lucky test."""
    now = datetime.now(UTC)
    backdated = now - timedelta(days=3)
    driver = FakeDriver(
        [step_record(1, 7, [checkin("partial", backdated)], now - timedelta(days=30))]
    )
    progress = await ProgressService(driver).compute("user-1", "skill-1", "UTC")

    assert progress.steps[0].last_checkin_at == backdated
    assert progress.steps[0].behind_cadence is True
    assert progress.streak_days == 0
