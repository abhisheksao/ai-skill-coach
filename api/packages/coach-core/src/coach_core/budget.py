"""The real Constitution-V queue behind the `acquire` seam (005 rewrite;
research.md R1; plan.md note 1). 001's v0 stub promised exactly this
replacement in its own docstring; call sites are unchanged.

Order inside `acquire`: kill switch (`user_limits.blocked`) -> effective
daily budget (`user_limits.daily_budget_override`, or the configured
default; 0 = effectively paused) -> atomic usage increment (existing
`increment_llm_usage` RPC) -> over-budget raises `BudgetExceeded` *before*
queueing -> `LlmQueue.admit()`. `report()` records actual post-call token
usage via `record_llm_tokens` -- zero-fallback when usage metadata is
absent (e.g. a degraded, validation-exhausted turn that never really
reached the provider).
"""

from datetime import UTC, datetime, timedelta

from coach_core.errors import BudgetExceeded
from coach_core.llm_queue import LlmQueue
from coach_core.supabase_rest import SupabaseRest


def _next_budget_reset(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


class BudgetGuard:
    def __init__(self, rest: SupabaseRest, daily_budget: int, queue: LlmQueue) -> None:
        self._rest = rest
        self._daily_budget = daily_budget
        self._queue = queue

    async def acquire(self, user_id: str) -> None:
        limits = await self._rest.select_one(
            "user_limits", {"user_id": user_id}, "daily_budget_override,blocked"
        )
        if limits and limits.get("blocked"):
            raise BudgetExceeded()  # kill switch: no automatic reset

        effective_budget = self._daily_budget
        if limits and limits.get("daily_budget_override") is not None:
            effective_budget = limits["daily_budget_override"]

        count = await self._rest.rpc("increment_llm_usage", {"uid": user_id})
        if int(count) > effective_budget:
            raise BudgetExceeded(resets_at=_next_budget_reset())

        await self._queue.admit()

    async def report(self, user_id: str, usage_metadata: dict | None) -> None:
        usage_metadata = usage_metadata or {}
        await self._rest.rpc(
            "record_llm_tokens",
            {
                "uid": user_id,
                "p_prompt": usage_metadata.get("prompt_tokens", 0),
                "p_output": usage_metadata.get("output_tokens", 0),
            },
        )
