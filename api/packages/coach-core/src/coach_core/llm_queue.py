"""Process-local rate-limit queue behind BudgetGuard.acquire (005,
Constitution V; research.md R1).

Two layers, both delay rather than reject: a semaphore (`LLM_MAX_CONCURRENT`)
serializes concurrent admission checks in FIFO order (Python's
`asyncio.Semaphore` services waiters in the order they started waiting), and
a token bucket (`LLM_MAX_RPM`) paces how fast calls are admitted against the
provider's rate limit. Only exceeding `LLM_QUEUE_MAX_WAIT_SECONDS` raises.

Design note: the semaphore is held only for the admission check itself, not
for the LLM call's duration. `BudgetGuard.acquire(user_id)` keeps its
existing no-return-value interface (plan.md note 1 — call sites never
change), so there is no seam for a caller to release a held slot once the
LLM call finishes. This still delivers the spec's real goal — a burst of
requests queues and paces out rather than all hammering the provider at
once — at the documented cost of not literally bounding in-flight call
count. A single always-warm process at ~100-user pilot scale (spec
Assumptions) makes this a reasonable trade.

Clock/sleep are injectable so tests exercise real pacing/timeout logic
without real sleeps (research.md R1 test requirement).
"""

import asyncio
import time
from collections.abc import Awaitable, Callable

from coach_core.errors import LlmUnavailable


class LlmQueue:
    def __init__(
        self,
        max_concurrent: int,
        max_rpm: int,
        max_wait_seconds: float,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_per_second = max_rpm / 60.0
        self._capacity = float(max_rpm)
        self._tokens = float(max_rpm)
        self._max_wait_seconds = max_wait_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_refill = clock()

    async def admit(self) -> None:
        started = self._clock()
        async with self._semaphore:
            self._refill()
            while self._tokens < 1:
                wait_for_token = (1 - self._tokens) / self._rate_per_second
                remaining_budget = self._max_wait_seconds - (self._clock() - started)
                if wait_for_token > remaining_budget:
                    raise LlmUnavailable()
                await self._sleep(wait_for_token)
                self._refill()
            self._tokens -= 1

    def _refill(self) -> None:
        now = self._clock()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate_per_second)
        self._last_refill = now
