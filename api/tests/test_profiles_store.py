"""ProfileStore.upsert: builds the row with server-stamped timestamps, and
falls back to the locally constructed row when the REST layer's
`return=representation` comes back empty (PostgREST can do this depending
on RLS/grant configuration) -- previously untested, so this fallback branch
was a documented-but-unverified assumption."""

import pytest

from skillcoach_api.services.profiles import ProfileStore

pytestmark = [pytest.mark.foundations, pytest.mark.profile]


class FakeRest:
    def __init__(self, returned: dict | None) -> None:
        self._returned = returned
        self.calls: list[tuple] = []

    async def upsert(self, table: str, row: dict, on_conflict: str) -> dict | None:
        self.calls.append((table, row, on_conflict))
        return self._returned


async def test_upsert_builds_row_with_timestamps_and_conflict_key() -> None:
    rest = FakeRest(returned={"user_id": "u1", "language": "hi"})
    store = ProfileStore(rest)

    result = await store.upsert("u1", "Priya", "hi", "Asia/Kolkata")

    table, row, on_conflict = rest.calls[0]
    assert table == "profiles"
    assert on_conflict == "user_id"
    assert row["user_id"] == "u1"
    assert row["display_name"] == "Priya"
    assert row["language"] == "hi"
    assert row["timezone"] == "Asia/Kolkata"
    assert row["consent_at"] == row["updated_at"]  # same stamp, ISO 8601
    assert result == {"user_id": "u1", "language": "hi"}  # returned row wins


async def test_upsert_falls_back_to_local_row_when_rest_returns_none() -> None:
    rest = FakeRest(returned=None)
    store = ProfileStore(rest)

    result = await store.upsert("u1", None, "en", "UTC")

    assert result["user_id"] == "u1"
    assert result["display_name"] is None
    assert result["language"] == "en"
    assert "consent_at" in result and "updated_at" in result
