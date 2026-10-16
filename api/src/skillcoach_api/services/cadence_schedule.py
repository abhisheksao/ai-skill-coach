"""Postgres projection of each active step's expected cadence
(research.md R8) — lets the nightly notification scan (routes/internal.py)
fan out with a plain SQL query over `cadence_schedules`, with no
full-graph Neo4j read needed just to enumerate candidates.
"""

from datetime import UTC, datetime

from coach_core.supabase_rest import SupabaseRest
from skillcoach_api.models.intents import StepPayload


class CadenceScheduleService:
    def __init__(self, rest: SupabaseRest) -> None:
        self._rest = rest

    async def sync(self, user_id: str, skill_id: str, steps: list[StepPayload]) -> None:
        """Called right after create_plan/revise_plan applies. Delete-all-
        then-insert-current: a revise_plan that drops a step order must not
        leave that row behind, and this trivially guarantees it — no
        row-by-row diffing needed."""
        await self._rest.delete("cadence_schedules", {"user_id": user_id, "skill_id": skill_id})
        if not steps:
            return
        now = datetime.now(UTC).isoformat()
        rows = [
            {
                "user_id": user_id,
                "skill_id": skill_id,
                "step_order": step.order,
                "cadence_per_week": step.cadence_per_week,
                "updated_at": now,
            }
            for step in steps
        ]
        await self._rest.insert("cadence_schedules", rows)

    async def all_rows(self) -> list[dict]:
        """Every (user_id, skill_id) with an active cadence schedule -- the
        nightly notification scan's fan-out entry point (research.md R1/
        R8): a plain SQL read, no Neo4j walk needed just to enumerate
        candidates."""
        return await self._rest.select_many("cadence_schedules", {}, "user_id,skill_id")
