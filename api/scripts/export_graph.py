"""Nightly graph export -> dated JSON -> private Supabase Storage bucket
(005, research.md R5; data-model.md). Full v1-schema serialization (every
node + relationship via generic Cypher, not per-label queries), an
independent counts aggregation for the restore spot-check, and a final
freshness assertion (today's object round-trips back out intact). Runs
OUTSIDE the API host (a scheduled GitHub Actions workflow) so backups
still happen when the backend itself is broken -- the exact scenario
backups exist for. Doubles as the Aura keep-alive touch.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime

import httpx
from neo4j.time import Date, DateTime, Time

from skillcoach_api.config import get_settings
from skillcoach_api.services.graph import GraphService

SCHEMA_VERSION = "v1"

_ALL_NODES = """
MATCH (n)
RETURN elementId(n) AS key, labels(n) AS labels, properties(n) AS properties
"""
_ALL_RELATIONSHIPS = """
MATCH (a)-[r]->(b)
RETURN elementId(a) AS start_key, elementId(b) AS end_key,
       type(r) AS type, properties(r) AS properties
"""
# Independent of the row dumps above -- a second, separate aggregation so
# the restore's spot-check verifies against a number the row dump didn't
# produce (data-model.md).
_NODE_COUNTS = "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count"
_REL_COUNTS = "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"


def _serialize_value(value):
    if isinstance(value, DateTime | Date | Time):
        # __temporal_type__ disambiguates on restore -- Date's iso_format()
        # ('2027-01-01') and Time's ('14:30:00.0') aren't valid DateTime
        # ISO strings, so restore_graph.py can't infer the right neo4j.time
        # class from the string alone (found via the T033 restore
        # rehearsal: any Date-typed property broke restore outright).
        return {"__temporal__": value.iso_format(), "__temporal_type__": type(value).__name__}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    return value


def _serialize_properties(properties: dict) -> dict:
    return {k: _serialize_value(v) for k, v in properties.items()}


async def export_graph(driver) -> dict:
    async with driver.session() as session:
        node_result = await session.run(_ALL_NODES)
        nodes = [
            {
                "key": r["key"],
                "labels": r["labels"],
                "properties": _serialize_properties(r["properties"]),
            }
            async for r in node_result
        ]

        rel_result = await session.run(_ALL_RELATIONSHIPS)
        relationships = [
            {
                "type": r["type"],
                "start_key": r["start_key"],
                "end_key": r["end_key"],
                "properties": _serialize_properties(r["properties"]),
            }
            async for r in rel_result
        ]

        node_count_result = await session.run(_NODE_COUNTS)
        node_counts = {r["label"]: r["count"] async for r in node_count_result}

        rel_count_result = await session.run(_REL_COUNTS)
        rel_counts = {r["type"]: r["count"] async for r in rel_count_result}

    return {
        "exported_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "schema_version": SCHEMA_VERSION,
        "counts": {"nodes": node_counts, "relationships": rel_counts},
        "nodes": nodes,
        "relationships": relationships,
    }


def _object_name(today: str) -> str:
    return f"graph-export-{today}.json"


async def upload_export(
    document: dict, supabase_url: str, service_role_key: str, http_client: httpx.AsyncClient
) -> str:
    """Uploads to the private graph-exports bucket via Supabase Storage's
    REST API (x-upsert so a re-run the same day overwrites cleanly).
    Raises on any failure -- surfaces as the workflow's missed-export
    alert (research.md R5); no silent partial state."""
    object_name = _object_name(datetime.now(UTC).date().isoformat())
    response = await http_client.post(
        f"{supabase_url.rstrip('/')}/storage/v1/object/graph-exports/{object_name}",
        content=json.dumps(document).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {service_role_key}",
            "apikey": service_role_key,
            "Content-Type": "application/json",
            "x-upsert": "true",
        },
    )
    response.raise_for_status()
    return object_name


async def verify_uploaded(
    object_name: str, supabase_url: str, service_role_key: str, http_client: httpx.AsyncClient
) -> bool:
    """Freshness assertion (research.md R5): re-download today's object
    and confirm it's non-empty, valid JSON, and the schema version
    matches -- not just "the upload call didn't raise"."""
    response = await http_client.get(
        f"{supabase_url.rstrip('/')}/storage/v1/object/graph-exports/{object_name}",
        headers={"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key},
    )
    response.raise_for_status()
    if not response.content:
        return False
    try:
        return json.loads(response.content).get("schema_version") == SCHEMA_VERSION
    except json.JSONDecodeError:
        return False


async def main() -> int:
    settings = get_settings()
    graph = GraphService.from_settings(settings)
    if graph.driver is None:
        print("Neo4j not configured; cannot export", file=sys.stderr)
        return 1

    try:
        document = await export_graph(graph.driver)
    finally:
        await graph.close()

    async with httpx.AsyncClient(timeout=60) as client:
        object_name = await upload_export(
            document, settings.supabase_url, settings.supabase_service_role_key, client
        )
        fresh = await verify_uploaded(
            object_name, settings.supabase_url, settings.supabase_service_role_key, client
        )

    if not fresh:
        print(f"Uploaded object {object_name} failed the freshness check", file=sys.stderr)
        return 1

    print(
        f"Exported {len(document['nodes'])} nodes, "
        f"{len(document['relationships'])} relationships -> {object_name}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
