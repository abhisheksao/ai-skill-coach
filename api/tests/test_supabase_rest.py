"""SupabaseRest: PostgREST request shaping (headers, params, response
parsing) via httpx.MockTransport — no real network. Negative path: any
non-2xx response must propagate as httpx.HTTPStatusError, never be
swallowed, since callers (MessageStore, ProfileStore, BudgetGuard) rely on
failures surfacing rather than silently no-op-ing."""

import httpx
import pytest

from coach_core.supabase_rest import SupabaseRest

pytestmark = [pytest.mark.foundations, pytest.mark.supabase]


def make_rest(handler) -> SupabaseRest:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SupabaseRest(client, "https://example.supabase.co", "service-key")


async def test_insert_posts_rows_with_return_minimal_header_and_apikey() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        return httpx.Response(201)

    await make_rest(handler).insert("messages", [{"sender": "user", "content": "hi"}])

    assert captured["url"] == "https://example.supabase.co/rest/v1/messages"
    assert captured["headers"]["prefer"] == "return=minimal"
    assert captured["headers"]["apikey"] == "service-key"
    assert captured["headers"]["authorization"] == "Bearer service-key"


async def test_upsert_sends_on_conflict_param_and_merge_header_returns_first_row() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["on_conflict"] == "user_id"
        assert request.headers["prefer"] == "resolution=merge-duplicates,return=representation"
        return httpx.Response(201, json=[{"user_id": "u1"}])

    row = await make_rest(handler).upsert("profiles", {"user_id": "u1"}, on_conflict="user_id")
    assert row == {"user_id": "u1"}


async def test_upsert_returns_none_on_empty_response() -> None:
    rest = make_rest(lambda r: httpx.Response(201, json=[]))
    assert await rest.upsert("profiles", {"user_id": "u1"}, on_conflict="user_id") is None


async def test_select_one_builds_eq_filters_and_limit_one() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["select"] == "language"
        assert request.url.params["user_id"] == "eq.u1"
        assert request.url.params["limit"] == "1"
        return httpx.Response(200, json=[{"language": "hi"}])

    row = await make_rest(handler).select_one("profiles", {"user_id": "u1"}, "language")
    assert row == {"language": "hi"}


async def test_select_one_returns_none_on_empty_response() -> None:
    rest = make_rest(lambda r: httpx.Response(200, json=[]))
    assert await rest.select_one("profiles", {"user_id": "missing"}, "language") is None


async def test_select_many_includes_order_and_limit_when_given() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["order"] == "created_at.desc"
        assert request.url.params["limit"] == "20"
        return httpx.Response(200, json=[{"id": "1"}, {"id": "2"}])

    rows = await make_rest(handler).select_many(
        "messages", {"session_id": "s1"}, "id", order="created_at.desc", limit=20
    )
    assert rows == [{"id": "1"}, {"id": "2"}]


async def test_select_many_omits_order_and_limit_when_not_given() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "order" not in request.url.params
        assert "limit" not in request.url.params
        return httpx.Response(200, json=[])

    await make_rest(handler).select_many("messages", {"session_id": "s1"}, "id")


async def test_select_many_merges_raw_filters_alongside_eq_filters() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["user_id"] == "eq.u1"
        assert request.url.params["sent_at"] == "gte.2026-07-01T00:00:00Z"
        return httpx.Response(200, json=[])

    await make_rest(handler).select_many(
        "notifications",
        {"user_id": "u1"},
        "id",
        raw_filters={"sent_at": "gte.2026-07-01T00:00:00Z"},
    )


async def test_update_sends_patch_with_eq_filters_and_return_minimal() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["filters"] = dict(request.url.params)
        captured["headers"] = request.headers
        return httpx.Response(204)

    await make_rest(handler).update(
        "push_tokens", {"user_id": "u1", "token": "t1"}, {"revoked_at": "now"}
    )

    assert captured["method"] == "PATCH"
    assert captured["filters"] == {"user_id": "eq.u1", "token": "eq.t1"}
    assert captured["headers"]["prefer"] == "return=minimal"


async def test_rpc_posts_to_rpc_path_and_returns_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.supabase.co/rest/v1/rpc/increment_budget"
        return httpx.Response(200, json={"allowed": True})

    result = await make_rest(handler).rpc("increment_budget", {"user_id": "u1"})
    assert result == {"allowed": True}


async def test_rpc_returns_none_for_void_function_204_no_content() -> None:
    """PostgREST 14+ answers a `returns void` function with 204 and an
    empty body; parsing that as JSON crashed every chat turn's token report
    (found by the fresh-database test, 2026-10-13)."""
    rest = make_rest(lambda request: httpx.Response(204))
    assert await rest.rpc("record_llm_tokens", {"uid": "u1"}) is None


async def test_rpc_returns_none_for_void_function_200_null() -> None:
    """Older PostgREST answered the same call with 200 `null`."""
    rest = make_rest(lambda request: httpx.Response(200, json=None))
    assert await rest.rpc("record_llm_tokens", {"uid": "u1"}) is None


@pytest.mark.parametrize("status", [400, 401, 404, 500, 503])
async def test_insert_raises_on_error_response(status: int) -> None:
    rest = make_rest(lambda r: httpx.Response(status))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.insert("messages", [{"a": 1}])


async def test_upsert_raises_on_error_response() -> None:
    rest = make_rest(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.upsert("profiles", {"a": 1}, on_conflict="user_id")


async def test_select_one_raises_on_error_response() -> None:
    rest = make_rest(lambda r: httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.select_one("profiles", {"user_id": "u1"}, "language")


async def test_select_many_raises_on_error_response() -> None:
    rest = make_rest(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.select_many("messages", {"session_id": "s1"}, "id")


async def test_update_raises_on_error_response() -> None:
    rest = make_rest(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.update("push_tokens", {"user_id": "u1"}, {"revoked_at": "now"})


async def test_delete_sends_eq_filters_and_return_minimal() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["filters"] = dict(request.url.params)
        captured["headers"] = request.headers
        return httpx.Response(204)

    await make_rest(handler).delete("cadence_schedules", {"user_id": "u1", "skill_id": "s1"})

    assert captured["method"] == "DELETE"
    assert captured["filters"] == {"user_id": "eq.u1", "skill_id": "eq.s1"}
    assert captured["headers"]["prefer"] == "return=minimal"


async def test_delete_raises_on_error_response() -> None:
    rest = make_rest(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.delete("cadence_schedules", {"user_id": "u1"})


async def test_rpc_raises_on_error_response() -> None:
    rest = make_rest(lambda r: httpx.Response(500))
    with pytest.raises(httpx.HTTPStatusError):
        await rest.rpc("increment_budget", {"user_id": "u1"})
