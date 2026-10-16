"""Operator account deletion (005, US5, research.md R13) -- against fake
stores: a user's graph subgraph is fully detach-deleted (scoped to that
user only, a second user's data untouched), Postgres rows removed per
the runbook's table list, and a non-existent user is a safe no-op."""

import httpx
import pytest
from scripts.delete_user import delete_user

pytestmark = [pytest.mark.hardening, pytest.mark.ops]

_ZERO_COUNTS = {"skills": 0, "goals": 0, "plans": 0, "steps": 0, "sessions": 0, "checkins": 0}


class FakeResult:
    def __init__(self, record: dict | None) -> None:
        self._record = record

    async def single(self):
        return self._record


class FakeSession:
    def __init__(self, driver: "FakeDriver") -> None:
        self._driver = driver

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def run(self, query: str, **params):
        self._driver.queries.append((query, params))
        user_id = params.get("user_id")
        if "RETURN" in query:
            return FakeResult(self._driver.counts_by_user.get(user_id, dict(_ZERO_COUNTS)))
        self._driver.deleted_users.append(user_id)
        return FakeResult(None)


class FakeDriver:
    def __init__(self, counts_by_user: dict | None = None) -> None:
        self.counts_by_user = counts_by_user or {}
        self.queries: list[tuple] = []
        self.deleted_users: list[str] = []

    def session(self) -> FakeSession:
        return FakeSession(self)


class FakeRest:
    def __init__(self) -> None:
        self.deletes: list[tuple] = []

    async def delete(self, table: str, filters: dict) -> None:
        self.deletes.append((table, filters))


def make_http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def ok_handler(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(204)


async def test_delete_user_removes_the_subgraph_and_postgres_rows_and_auth_user() -> None:
    driver = FakeDriver(
        counts_by_user={
            "user-1": {
                "skills": 2,
                "goals": 2,
                "plans": 2,
                "steps": 6,
                "sessions": 3,
                "checkins": 10,
            }
        }
    )
    rest = FakeRest()

    counts = await delete_user(
        driver, rest, make_http(ok_handler), "https://proj.supabase.co", "service-key", "user-1"
    )

    assert counts["skills"] == 2
    assert driver.deleted_users == ["user-1"]
    deletes_by_table = dict(rest.deletes)
    assert set(deletes_by_table) == {
        "messages",
        "llm_usage",
        "push_tokens",
        "notifications",
        "cadence_schedules",
        "user_limits",
        "analytics_events",
        "profiles",
    }
    # analytics_events has no user_id column (migration 20260718000001) --
    # its pseudonymous subject column is user_sub; every other table
    # filters on user_id.
    assert deletes_by_table["analytics_events"] == {"user_sub": "user-1"}
    assert all(
        f == {"user_id": "user-1"} for t, f in rest.deletes if t != "analytics_events"
    )


async def test_second_user_is_never_touched() -> None:
    driver = FakeDriver()
    rest = FakeRest()

    await delete_user(
        driver, rest, make_http(ok_handler), "https://proj.supabase.co", "service-key", "user-1"
    )

    # Every query/delete this run issued is parameterized to user-1 only
    # (analytics_events' filter value lives under "user_sub", not
    # "user_id" -- check both keys explicitly).
    assert all(params.get("user_id") != "user-2" for _, params in driver.queries)
    assert all(f.get("user_id") != "user-2" for _, f in rest.deletes)
    assert all(f.get("user_sub") != "user-2" for _, f in rest.deletes)


async def test_nonexistent_user_is_a_safe_no_op() -> None:
    driver = FakeDriver()  # no counts seeded for "ghost-user"
    rest = FakeRest()

    counts = await delete_user(
        driver,
        rest,
        make_http(ok_handler),
        "https://proj.supabase.co",
        "service-key",
        "ghost-user",
    )

    assert counts == _ZERO_COUNTS
    assert driver.deleted_users == ["ghost-user"]  # DETACH DELETE ran, matched nothing, no error


async def test_missing_auth_user_404_is_treated_as_already_deleted() -> None:
    driver = FakeDriver()
    rest = FakeRest()

    def not_found_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    await delete_user(
        driver,
        rest,
        make_http(not_found_handler),
        "https://proj.supabase.co",
        "service-key",
        "ghost-user",
    )  # must not raise


async def test_auth_user_delete_failure_raises() -> None:
    driver = FakeDriver()
    rest = FakeRest()

    def failing_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(httpx.HTTPStatusError):
        await delete_user(
            driver,
            rest,
            make_http(failing_handler),
            "https://proj.supabase.co",
            "service-key",
            "user-1",
        )
