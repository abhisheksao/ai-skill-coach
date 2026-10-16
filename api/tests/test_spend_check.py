"""spend_check.py: threshold logic against ops_daily_spend (005,
research.md R6)."""

import pytest
from scripts.spend_check import check_spend

pytestmark = [pytest.mark.hardening, pytest.mark.ops]


class FakeRest:
    def __init__(self, row: dict | None = None) -> None:
        self.row = row
        self.select_calls: list[tuple[str, dict, str]] = []

    async def select_one(self, table: str, filters: dict, columns: str) -> dict | None:
        self.select_calls.append((table, filters, columns))
        return self.row


async def test_under_threshold_not_breached() -> None:
    rest = FakeRest(row={"estimated_usd": 1.23})
    spend, breached = await check_spend(rest, threshold_usd=5.0)
    assert spend == 1.23
    assert breached is False
    assert rest.select_calls[0][0] == "ops_daily_spend"


async def test_over_threshold_breached() -> None:
    rest = FakeRest(row={"estimated_usd": 12.5})
    spend, breached = await check_spend(rest, threshold_usd=5.0)
    assert spend == 12.5
    assert breached is True


async def test_missing_view_data_treated_as_zero_spend() -> None:
    """No row for today yet (no calls made) -- not an error, just $0."""
    rest = FakeRest(row=None)
    spend, breached = await check_spend(rest, threshold_usd=5.0)
    assert spend == 0.0
    assert breached is False
