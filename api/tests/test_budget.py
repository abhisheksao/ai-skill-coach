"""BudgetGuard: kill switch + per-user override + atomic counter vs daily
limit, then LlmQueue admission; report() records post-call tokens (005
rewrite; Constitution V; research.md R1)."""

import pytest

from coach_core.budget import BudgetGuard
from coach_core.errors import BudgetExceeded

pytestmark = [pytest.mark.hardening, pytest.mark.budget]


class FakeRest:
    def __init__(self, counts: list[int] | None = None, user_limits: dict | None = None) -> None:
        self._counts = iter(counts or [])
        self.user_limits = user_limits  # None = no row (defaults apply)
        self.rpc_calls: list[tuple[str, dict]] = []
        self.select_calls: list[tuple[str, dict]] = []

    async def select_one(self, table: str, filters: dict, columns: str) -> dict | None:
        self.select_calls.append((table, filters))
        return self.user_limits

    async def rpc(self, function: str, payload: dict):
        self.rpc_calls.append((function, payload))
        if function == "increment_llm_usage":
            return next(self._counts)
        return None


class FakeQueue:
    def __init__(self) -> None:
        self.admit_calls = 0

    async def admit(self) -> None:
        self.admit_calls += 1


async def test_under_budget_admits_to_queue() -> None:
    rest = FakeRest(counts=[1, 2, 50])
    queue = FakeQueue()
    guard = BudgetGuard(rest, daily_budget=50, queue=queue)
    for _ in range(3):
        await guard.acquire("user-1")
    assert queue.admit_calls == 3
    assert [c[0] for c in rest.rpc_calls] == ["increment_llm_usage"] * 3
    assert rest.rpc_calls[0][1] == {"uid": "user-1"}


async def test_over_budget_raises_before_queueing() -> None:
    rest = FakeRest(counts=[51])
    queue = FakeQueue()
    guard = BudgetGuard(rest, daily_budget=50, queue=queue)
    with pytest.raises(BudgetExceeded):
        await guard.acquire("user-1")
    assert queue.admit_calls == 0


async def test_over_budget_resets_at_is_next_utc_midnight() -> None:
    rest = FakeRest(counts=[51])
    guard = BudgetGuard(rest, daily_budget=50, queue=FakeQueue())
    with pytest.raises(BudgetExceeded) as exc_info:
        await guard.acquire("user-1")
    resets_at = exc_info.value.resets_at
    assert resets_at is not None
    assert (resets_at.hour, resets_at.minute, resets_at.second) == (0, 0, 0)


async def test_daily_budget_override_honored() -> None:
    rest = FakeRest(counts=[5], user_limits={"daily_budget_override": 3, "blocked": False})
    guard = BudgetGuard(rest, daily_budget=50, queue=FakeQueue())
    with pytest.raises(BudgetExceeded):
        # 5 > override of 3, even though comfortably under the default 50.
        await guard.acquire("user-1")


async def test_daily_budget_override_zero_pauses_immediately() -> None:
    rest = FakeRest(counts=[1], user_limits={"daily_budget_override": 0, "blocked": False})
    guard = BudgetGuard(rest, daily_budget=50, queue=FakeQueue())
    with pytest.raises(BudgetExceeded):
        await guard.acquire("user-1")


async def test_blocked_raises_immediately_without_incrementing_usage() -> None:
    rest = FakeRest(user_limits={"daily_budget_override": None, "blocked": True})
    queue = FakeQueue()
    guard = BudgetGuard(rest, daily_budget=50, queue=queue)
    with pytest.raises(BudgetExceeded) as exc_info:
        await guard.acquire("user-1")
    assert exc_info.value.resets_at is None  # no automatic reset for a kill switch
    assert rest.rpc_calls == []  # never reaches the usage counter
    assert queue.admit_calls == 0


async def test_absence_of_user_limits_row_means_defaults() -> None:
    rest = FakeRest(counts=[10], user_limits=None)
    queue = FakeQueue()
    guard = BudgetGuard(rest, daily_budget=50, queue=queue)
    await guard.acquire("user-1")  # 10 <= default 50, no override/block to consider
    assert queue.admit_calls == 1


async def test_report_records_tokens_via_rpc() -> None:
    rest = FakeRest()
    guard = BudgetGuard(rest, daily_budget=50, queue=FakeQueue())
    await guard.report("user-1", {"prompt_tokens": 120, "output_tokens": 40})
    assert rest.rpc_calls == [
        ("record_llm_tokens", {"uid": "user-1", "p_prompt": 120, "p_output": 40})
    ]


async def test_report_zero_fallback_when_usage_metadata_absent() -> None:
    rest = FakeRest()
    guard = BudgetGuard(rest, daily_budget=50, queue=FakeQueue())
    await guard.report("user-1", None)
    assert rest.rpc_calls == [
        ("record_llm_tokens", {"uid": "user-1", "p_prompt": 0, "p_output": 0})
    ]
