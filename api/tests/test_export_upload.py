"""Supabase Storage upload for the graph export (005, research.md R5):
correct bucket/object name, service-role auth header, and a failure
propagates loudly (drives the workflow's missed-export alert)."""

from datetime import UTC, datetime

import httpx
import pytest
from scripts.export_graph import upload_export, verify_uploaded

pytestmark = [pytest.mark.hardening, pytest.mark.ops]

TODAY = datetime.now(UTC).date().isoformat()


def make_http(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_upload_targets_the_dated_object_with_service_role_auth() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200)

    object_name = await upload_export(
        {"schema_version": "v1"}, "https://proj.supabase.co", "service-key", make_http(handler)
    )

    assert object_name == f"graph-export-{TODAY}.json"
    request = captured[0]
    assert request.url.path == f"/storage/v1/object/graph-exports/graph-export-{TODAY}.json"
    assert request.headers["Authorization"] == "Bearer service-key"
    assert request.headers["apikey"] == "service-key"
    assert request.headers["x-upsert"] == "true"


async def test_upload_failure_raises() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with pytest.raises(httpx.HTTPStatusError):
        await upload_export(
            {"schema_version": "v1"}, "https://proj.supabase.co", "service-key", make_http(handler)
        )


async def test_verify_uploaded_true_when_schema_version_matches() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"schema_version": "v1", "nodes": []})

    fresh = await verify_uploaded(
        "graph-export-2026-07-19.json",
        "https://proj.supabase.co",
        "service-key",
        make_http(handler),
    )
    assert fresh is True


async def test_verify_uploaded_false_when_body_is_empty() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"")

    fresh = await verify_uploaded(
        "graph-export-2026-07-19.json",
        "https://proj.supabase.co",
        "service-key",
        make_http(handler),
    )
    assert fresh is False


async def test_verify_uploaded_raises_on_download_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        await verify_uploaded(
            "graph-export-2026-07-19.json",
            "https://proj.supabase.co",
            "service-key",
            make_http(handler),
        )
