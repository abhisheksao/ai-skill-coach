"""LlmQueue: FIFO admission, token-bucket pacing, and
LLM_QUEUE_MAX_WAIT_SECONDS timeout -> LlmUnavailable (005, research.md R1).
Fake clock/sleep only -- no real sleeps."""

import asyncio

import pytest

from coach_core.errors import LlmUnavailable
from coach_core.llm_queue import LlmQueue

pytestmark = [pytest.mark.hardening, pytest.mark.queue]


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_sleep(clock: FakeClock):
    async def _sleep(seconds: float) -> None:
        clock.advance(seconds)
        await asyncio.sleep(0)  # real scheduler yield so concurrent tasks interleave

    return _sleep


async def test_admits_immediately_when_bucket_has_capacity() -> None:
    clock = FakeClock()
    sleep_calls: list[float] = []

    async def tracking_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    queue = LlmQueue(
        max_concurrent=4, max_rpm=60, max_wait_seconds=10, clock=clock, sleep=tracking_sleep
    )
    await queue.admit()

    assert sleep_calls == []


async def test_waits_for_token_bucket_refill_then_admits() -> None:
    clock = FakeClock()
    queue = LlmQueue(
        max_concurrent=4, max_rpm=1, max_wait_seconds=100, clock=clock, sleep=make_sleep(clock)
    )

    await queue.admit()  # drains the single starting token
    await queue.admit()  # must wait ~60s for one token to refill, then proceed

    assert clock.now == pytest.approx(60.0)


async def test_exceeding_max_wait_raises_llm_unavailable() -> None:
    clock = FakeClock()
    sleep_calls: list[float] = []

    async def tracking_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock.advance(seconds)

    queue = LlmQueue(
        max_concurrent=4, max_rpm=1, max_wait_seconds=10, clock=clock, sleep=tracking_sleep
    )

    await queue.admit()  # drains the single starting token
    with pytest.raises(LlmUnavailable):
        await queue.admit()  # needs ~60s but only 10s of budget remains

    assert sleep_calls == []  # gives up before ever sleeping past budget


async def test_fifo_and_concurrency_cap_serialize_a_burst() -> None:
    """max_concurrent=1 fully serializes admission: proves BOTH FIFO order
    (workers complete in creation order) and the concurrency cap (no two
    admits ever overlap -- each completion time is strictly later than the
    last, since every worker here is forced to wait for a fresh refill)."""
    clock = FakeClock()
    queue = LlmQueue(
        max_concurrent=1, max_rpm=1, max_wait_seconds=1000, clock=clock, sleep=make_sleep(clock)
    )
    completions: list[tuple[int, float]] = []

    async def worker(i: int) -> None:
        await queue.admit()
        completions.append((i, clock.now))

    await queue.admit()  # drain the starting token so every burst member must wait
    tasks = [asyncio.create_task(worker(i)) for i in range(4)]
    await asyncio.gather(*tasks)

    assert [i for i, _ in completions] == [0, 1, 2, 3]
    times = [t for _, t in completions]
    assert times == sorted(times)
    assert len(set(times)) == 4  # each waited its own full turn, none overlapped
