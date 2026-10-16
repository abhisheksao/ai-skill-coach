"""CadenceScheduleService: Postgres cadence-schedule sync on
create_plan/revise_plan (research.md R8)."""

import pytest

from skillcoach_api.models.intents import StepPayload
from skillcoach_api.services.cadence_schedule import CadenceScheduleService

pytestmark = [pytest.mark.progress_notifications, pytest.mark.cadence]


class FakeRest:
    def __init__(self, many_rows: list[dict] | None = None) -> None:
        self.deletes: list[tuple[str, dict]] = []
        self.inserts: list[tuple[str, list[dict]]] = []
        self.many_calls: list[tuple] = []
        self._many_rows = many_rows or []

    async def delete(self, table: str, filters: dict) -> None:
        self.deletes.append((table, filters))

    async def insert(self, table: str, rows: list[dict]) -> None:
        self.inserts.append((table, rows))

    async def select_many(self, table: str, filters: dict, columns: str, **kwargs) -> list[dict]:
        self.many_calls.append((table, filters, columns))
        return self._many_rows


STEPS = [
    StepPayload(order=1, description="Float", cadence_per_week=3),
    StepPayload(order=2, description="Kick", cadence_per_week=2),
]


async def test_sync_deletes_existing_rows_then_inserts_one_per_step() -> None:
    rest = FakeRest()
    await CadenceScheduleService(rest).sync("user-1", "skill-1", STEPS)

    assert rest.deletes == [("cadence_schedules", {"user_id": "user-1", "skill_id": "skill-1"})]
    table, rows = rest.inserts[0]
    assert table == "cadence_schedules"
    assert len(rows) == 2
    assert rows[0]["step_order"] == 1
    assert rows[0]["cadence_per_week"] == 3
    assert all(r["user_id"] == "user-1" and r["skill_id"] == "skill-1" for r in rows)


async def test_sync_with_fewer_steps_than_before_only_inserts_current_ones() -> None:
    """A revise_plan that drops a step must not leave the old step_order's
    row behind -- delete-all-then-insert-current achieves this trivially,
    with no diffing against what was previously stored."""
    rest = FakeRest()
    await CadenceScheduleService(rest).sync("user-1", "skill-1", STEPS[:1])

    _, rows = rest.inserts[0]
    assert [r["step_order"] for r in rows] == [1]


async def test_sync_with_no_steps_deletes_but_inserts_nothing() -> None:
    rest = FakeRest()
    await CadenceScheduleService(rest).sync("user-1", "skill-1", [])

    assert rest.deletes
    assert rest.inserts == []


async def test_all_rows_reads_the_whole_table_with_no_user_filter() -> None:
    rest = FakeRest(
        many_rows=[{"user_id": "u1", "skill_id": "s1"}, {"user_id": "u2", "skill_id": "s2"}]
    )
    rows = await CadenceScheduleService(rest).all_rows()

    assert rows == [{"user_id": "u1", "skill_id": "s1"}, {"user_id": "u2", "skill_id": "s2"}]
    table, filters, columns = rest.many_calls[0]
    assert table == "cadence_schedules"
    assert filters == {}  # fan-out entry point -- every user's rows, not scoped to one
