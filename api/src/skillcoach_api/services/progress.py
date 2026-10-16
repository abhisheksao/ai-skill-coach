"""Progress derivation (Constitution II; research.md R7) -- completed
steps, streak, and per-step cadence adherence computed on demand from
`CheckIn` nodes every call. No counter is ever written or cached anywhere;
recomputing from the same CheckIns always reproduces the same numbers
(FR-004, SC-002).
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from skillcoach_api import constants

# One row per Step in the skill's ACTIVE (non-superseded) Plan, with every
# CheckIn ever recorded against it (OPTIONAL MATCH -- collect(c) yields []
# when none exist, Cypher skips nulls). p.created_at is the fallback anchor
# for a step that has never had a check-in (mirrors research.md R9's
# dashboard staleness fallback: "or the skill's created_at if none yet").
_SKILL_CHECKINS = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_PLAN]->(p:Plan) WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
MATCH (p)-[:HAS_STEP]->(st:Step)
OPTIONAL MATCH (st)<-[:FOR_STEP]-(c:CheckIn)
WITH p, st, collect(c) AS checkins
RETURN st.order AS step_order, st.cadence_per_week AS cadence_per_week,
       checkins, p.created_at AS plan_created_at
ORDER BY st.order ASC
"""


def _native(value):
    """Neo4j temporal types expose .to_native(); plain values pass through."""
    return value.to_native() if hasattr(value, "to_native") else value


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _to_local_date(value: datetime, tz: ZoneInfo) -> date:
    return _as_aware_utc(value).astimezone(tz).date()


def _is_behind_cadence(anchor: datetime, cadence_per_week: int, now: datetime) -> bool:
    expected_interval_days = 7 / cadence_per_week
    threshold = timedelta(days=constants.CADENCE_BEHIND_MULTIPLIER * expected_interval_days)
    return (now - _as_aware_utc(anchor)) > threshold


def _current_streak(dates: set[date], tz: ZoneInfo, now: datetime) -> int:
    """Longest consecutive run of distinct calendar dates ending today or
    yesterday (research.md R7) -- a run that stopped earlier than yesterday
    is a broken streak, reported as 0, not "however long it used to be"."""
    if not dates:
        return 0
    today = now.astimezone(tz).date()
    most_recent = max(dates)
    if most_recent not in (today, today - timedelta(days=1)):
        return 0
    streak = 0
    cursor = most_recent
    while cursor in dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


@dataclass
class StepProgress:
    order: int
    completed: bool
    behind_cadence: bool
    last_checkin_at: datetime | None
    # The timestamp behind_cadence was actually measured from -- same as
    # last_checkin_at when a check-in exists, else the Plan's created_at.
    # Internal-only (not part of the public progress/dashboard API shape,
    # T033); the notification scan (T026) uses this to compute "days
    # since" even for a step that's never had a single check-in.
    anchor_at: datetime


@dataclass
class SkillProgress:
    skill_id: str
    completed_steps: list[int]
    total_steps: int
    streak_days: int
    steps: list[StepProgress]


class ProgressService:
    def __init__(self, driver) -> None:
        self._driver = driver

    async def compute(self, user_id: str, skill_id: str, timezone: str) -> SkillProgress:
        async with self._driver.session() as session:
            result = await session.run(_SKILL_CHECKINS, user_id=user_id, skill_id=skill_id)
            records = [record async for record in result]

        now = datetime.now(UTC)
        tz = ZoneInfo(timezone)

        completed_steps: list[int] = []
        steps: list[StepProgress] = []
        all_dates: set[date] = set()

        for record in records:
            checkins = [dict(c) for c in record["checkins"]]
            timestamps = [_native(c["timestamp"]) for c in checkins]
            for ts in timestamps:
                all_dates.add(_to_local_date(ts, tz))

            completed = any(c["outcome"] == "completed" for c in checkins)
            if completed:
                completed_steps.append(record["step_order"])

            last_checkin_at = max(timestamps) if timestamps else None
            anchor = last_checkin_at or _native(record["plan_created_at"])

            steps.append(
                StepProgress(
                    order=record["step_order"],
                    completed=completed,
                    behind_cadence=_is_behind_cadence(anchor, record["cadence_per_week"], now),
                    last_checkin_at=last_checkin_at,
                    anchor_at=_as_aware_utc(anchor),
                )
            )

        return SkillProgress(
            skill_id=skill_id,
            completed_steps=completed_steps,
            total_steps=len(records),
            streak_days=_current_streak(all_dates, tz, now),
            steps=steps,
        )
