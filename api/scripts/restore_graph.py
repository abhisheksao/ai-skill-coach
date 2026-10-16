"""Replay a graph export (export_graph.py) into an empty Neo4j instance
(005, research.md R5; data-model.md). Refuses a non-empty target unless
explicitly overridden. Validates the whole document up front -- a
malformed artifact fails loudly before any write happens, never a
partial restore. Reports node/relationship counts against the artifact's
own independently-aggregated `counts` and exits non-zero on mismatch
(the restore rehearsal's spot-check, SC-003).
"""

import argparse
import asyncio
import json
import sys

from neo4j import AsyncGraphDatabase
from neo4j.time import Date, DateTime, Time

_TEMPORAL_TYPES = {"Date": Date, "Time": Time, "DateTime": DateTime}

# Trusted allowlists (constitution's fixed v1 schema) -- labels/types are
# interpolated into Cypher query text (Cypher can't parameterize labels or
# relationship types), so a corrupted or hand-edited artifact can never
# inject arbitrary Cypher through this path.
_KNOWN_LABELS = {"User", "Skill", "Goal", "Plan", "Step", "Session", "CheckIn"}
_KNOWN_REL_TYPES = {
    "PURSUES",
    "HAS_GOAL",
    "SUPERSEDES",
    "HAS_PLAN",
    "HAS_STEP",
    "FOR_GOAL",
    "HAS_SESSION",
    "FOR_STEP",
}

_COUNT_EXISTING_NODES = "MATCH (n) RETURN count(n) AS count"
_NODE_COUNTS = "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS count"
_REL_COUNTS = "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"


class MalformedExport(Exception):
    pass


def _validate_document(document: dict) -> None:
    if document.get("schema_version") != "v1":
        raise MalformedExport(f"unexpected schema_version: {document.get('schema_version')!r}")
    for key in ("nodes", "relationships", "counts"):
        if key not in document:
            raise MalformedExport(f"missing required key: {key!r}")
    for node in document["nodes"]:
        if not set(node.get("labels", [])) <= _KNOWN_LABELS:
            raise MalformedExport(f"unknown node label(s): {node.get('labels')!r}")
        _validate_properties_deserializable(node.get("properties", {}))
    for rel in document["relationships"]:
        if rel.get("type") not in _KNOWN_REL_TYPES:
            raise MalformedExport(f"unknown relationship type: {rel.get('type')!r}")
        _validate_properties_deserializable(rel.get("properties", {}))


def _validate_properties_deserializable(properties: dict) -> None:
    """Eagerly deserializes (and discards the result) so a bad __temporal__
    value fails here, before any write -- otherwise it would only surface
    mid-restore, inside the node/relationship creation loop, leaving a
    partial write behind despite this module's no-partial-restore
    guarantee (found via the T033 restore rehearsal)."""
    try:
        _deserialize_properties(properties)
    except (ValueError, KeyError) as exc:
        raise MalformedExport(f"unparseable property value: {exc}") from exc


def _deserialize_value(value):
    if isinstance(value, dict) and "__temporal__" in value:
        iso = value["__temporal__"]
        # __temporal_type__ (added after the T033 restore rehearsal found
        # Date-typed properties broke restore) picks the right neo4j.time
        # class directly. Older artifacts exported before that fix have no
        # type tag -- fall back to inferring from the ISO string's shape:
        # Date is exactly YYYY-MM-DD, Time has no '-' date component,
        # anything else is a DateTime.
        temporal_type = value.get("__temporal_type__")
        if temporal_type in _TEMPORAL_TYPES:
            return _TEMPORAL_TYPES[temporal_type].from_iso_format(iso)
        if len(iso) == 10 and iso.count("-") == 2:
            return Date.from_iso_format(iso)
        if "-" not in iso:
            return Time.from_iso_format(iso)
        return DateTime.from_iso_format(iso)
    if isinstance(value, list):
        return [_deserialize_value(v) for v in value]
    return value


def _deserialize_properties(properties: dict) -> dict:
    return {k: _deserialize_value(v) for k, v in properties.items()}


async def _assert_target_empty(driver, force_empty_check_off: bool) -> None:
    if force_empty_check_off:
        return
    async with driver.session() as session:
        result = await session.run(_COUNT_EXISTING_NODES)
        record = await result.single()
    if record["count"] > 0:
        raise MalformedExport(
            "target instance is not empty (pass force_empty_check_off=True to override)"
        )


async def restore_graph(driver, document: dict, force_empty_check_off: bool = False) -> dict:
    """Returns {"nodes": {...}, "relationships": {...}} -- the RESTORED
    instance's own independently-aggregated counts, for the caller to
    compare against document["counts"]."""
    _validate_document(document)
    await _assert_target_empty(driver, force_empty_check_off)

    key_map: dict[str, str] = {}
    async with driver.session() as session:
        for node in document["nodes"]:
            label_clause = ":".join(node["labels"])
            query = f"CREATE (n:{label_clause}) SET n = $properties RETURN elementId(n) AS new_key"
            result = await session.run(
                query, properties=_deserialize_properties(node["properties"])
            )
            record = await result.single()
            key_map[node["key"]] = record["new_key"]

        for rel in document["relationships"]:
            query = (
                "MATCH (a), (b) WHERE elementId(a) = $start AND elementId(b) = $end "
                f"CREATE (a)-[r:{rel['type']}]->(b) SET r = $properties"
            )
            await session.run(
                query,
                start=key_map[rel["start_key"]],
                end=key_map[rel["end_key"]],
                properties=_deserialize_properties(rel["properties"]),
            )

        node_count_result = await session.run(_NODE_COUNTS)
        node_counts = {r["label"]: r["count"] async for r in node_count_result}
        rel_count_result = await session.run(_REL_COUNTS)
        rel_counts = {r["type"]: r["count"] async for r in rel_count_result}

    return {"nodes": node_counts, "relationships": rel_counts}


def _counts_match(expected: dict, actual: dict) -> bool:
    expected_nodes = {k: v for k, v in expected["nodes"].items() if v}
    expected_rels = {k: v for k, v in expected["relationships"].items() if v}
    return expected_nodes == actual["nodes"] and expected_rels == actual["relationships"]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, help="Path to a graph-export-*.json artifact")
    parser.add_argument("--uri", required=True, help="Target Neo4j instance URI")
    parser.add_argument("--user", default="neo4j")
    parser.add_argument("--password", required=True)
    parser.add_argument(
        "--force-empty-check-off",
        action="store_true",
        help="Skip the refuse-non-empty-target safety check",
    )
    return parser.parse_args()


async def main(args: argparse.Namespace, document: dict) -> int:
    driver = AsyncGraphDatabase.driver(args.uri, auth=(args.user, args.password))
    try:
        actual_counts = await restore_graph(driver, document, args.force_empty_check_off)
    except MalformedExport as exc:
        print(f"Refusing to restore: {exc}", file=sys.stderr)
        return 1
    finally:
        await driver.close()

    print(f"Restored: nodes={actual_counts['nodes']} rels={actual_counts['relationships']}")
    if not _counts_match(document["counts"], actual_counts):
        print(
            f"COUNT MISMATCH -- expected {document['counts']}, got {actual_counts}",
            file=sys.stderr,
        )
        return 1

    print("Counts match the artifact's independent aggregation. Restore verified.")
    return 0


if __name__ == "__main__":
    _args = _parse_args()
    with open(_args.file) as _f:
        _document = json.load(_f)
    sys.exit(asyncio.run(main(_args, _document)))
