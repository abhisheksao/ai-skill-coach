"""Export/restore round-trip against fake driver-level fakes (005,
research.md R5; data-model.md) -- no real Neo4j needed. The round-trip
against a real scratch instance is the human-executed rehearsal (T033)."""

import pytest
from neo4j.time import Date, DateTime, Time
from scripts.export_graph import _serialize_value, export_graph
from scripts.restore_graph import MalformedExport, _deserialize_value, restore_graph

pytestmark = [pytest.mark.hardening, pytest.mark.ops]


class FakeResult:
    def __init__(self, records: list[dict]) -> None:
        self._records = records

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for r in self._records:
            yield r

    async def single(self):
        return self._records[0]


class FakeSession:
    def __init__(self, queue: list[list[dict]]) -> None:
        self._queue = queue
        self.queries: list[str] = []

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *args) -> bool:
        return False

    async def run(self, query: str, **params):
        self.queries.append(query)
        return FakeResult(self._queue.pop(0))


class FakeDriver:
    def __init__(self, queue: list[list[dict]]) -> None:
        self._queue = queue

    def session(self) -> FakeSession:
        return FakeSession(self._queue)


def _user_node(key: str) -> dict:
    return {"key": key, "labels": ["User"], "properties": {"id": "user-1"}}


def _skill_node(key: str) -> dict:
    return {"key": key, "labels": ["Skill"], "properties": {"id": "skill-1", "name": "Swimming"}}


async def test_export_produces_the_documented_shape() -> None:
    driver = FakeDriver(
        [
            [_user_node("n1"), _skill_node("n2")],  # all-nodes dump
            [{"type": "PURSUES", "start_key": "n1", "end_key": "n2", "properties": {}}],
            [{"label": "User", "count": 1}, {"label": "Skill", "count": 1}],  # independent counts
            [{"type": "PURSUES", "count": 1}],
        ]
    )
    document = await export_graph(driver)

    assert document["schema_version"] == "v1"
    assert document["counts"] == {
        "nodes": {"User": 1, "Skill": 1},
        "relationships": {"PURSUES": 1},
    }
    assert len(document["nodes"]) == 2
    assert len(document["relationships"]) == 1
    assert "exported_at" in document


async def test_restore_replays_nodes_and_relationships_and_counts_match() -> None:
    document = {
        "schema_version": "v1",
        "counts": {"nodes": {"User": 1, "Skill": 1}, "relationships": {"PURSUES": 1}},
        "nodes": [_user_node("old-n1"), _skill_node("old-n2")],
        "relationships": [
            {"type": "PURSUES", "start_key": "old-n1", "end_key": "old-n2", "properties": {}}
        ],
    }
    driver = FakeDriver(
        [
            [{"new_key": "new-n1"}],  # create User
            [{"new_key": "new-n2"}],  # create Skill
            [{}],  # create PURSUES relationship (result unconsumed)
            [{"label": "User", "count": 1}, {"label": "Skill", "count": 1}],
            [{"type": "PURSUES", "count": 1}],
        ]
    )

    actual_counts = await restore_graph(driver, document, force_empty_check_off=True)

    assert actual_counts == {"nodes": {"User": 1, "Skill": 1}, "relationships": {"PURSUES": 1}}


async def test_restore_refuses_a_non_empty_target() -> None:
    document = {
        "schema_version": "v1",
        "nodes": [],
        "relationships": [],
        "counts": {"nodes": {}, "relationships": {}},
    }
    driver = FakeDriver([[{"count": 3}]])  # target already has 3 nodes

    with pytest.raises(MalformedExport):
        await restore_graph(driver, document, force_empty_check_off=False)


async def test_malformed_artifact_fails_loudly_before_any_write() -> None:
    document = {"schema_version": "v2", "nodes": [], "relationships": [], "counts": {}}
    driver = FakeDriver([])  # no results queued -- proves no query is ever run

    with pytest.raises(MalformedExport):
        await restore_graph(driver, document, force_empty_check_off=True)


async def test_unknown_node_label_rejected_before_any_write() -> None:
    document = {
        "schema_version": "v1",
        "nodes": [{"key": "n1", "labels": ["EvilLabel"], "properties": {}}],
        "relationships": [],
        "counts": {"nodes": {}, "relationships": {}},
    }
    driver = FakeDriver([])

    with pytest.raises(MalformedExport):
        await restore_graph(driver, document, force_empty_check_off=True)


@pytest.mark.parametrize(
    "value",
    [Date(2027, 1, 1), Time(14, 30, 0), DateTime(2026, 7, 14, 18, 22, 30, 253000000)],
    ids=["Date", "Time", "DateTime"],
)
def test_temporal_round_trips_through_serialize_deserialize(value) -> None:
    """T033 restore rehearsal found that a Date-typed property (e.g. a
    goal's target date) broke restore outright: export wrapped Date, Time,
    and DateTime under the same untagged `__temporal__` key, and restore
    always deserialized as DateTime, which can't parse a bare date string.
    """
    restored = _deserialize_value(_serialize_value(value))

    assert restored == value
    assert type(restored) is type(value)


def test_temporal_deserialize_falls_back_for_pre_fix_artifacts_without_type_tag() -> None:
    """Artifacts exported before __temporal_type__ existed (e.g. the very
    first nightly export) have no type tag -- deserialization must still
    infer the right type from the ISO string's shape."""
    assert _deserialize_value({"__temporal__": "2027-01-01"}) == Date(2027, 1, 1)
    assert _deserialize_value({"__temporal__": "14:30:00.000000000"}) == Time(14, 30, 0)
    assert _deserialize_value(
        {"__temporal__": "2026-07-14T18:22:30.253000000"}
    ) == DateTime(2026, 7, 14, 18, 22, 30, 253000000)


async def test_malformed_temporal_value_rejected_before_any_write() -> None:
    """Previously, a bad __temporal__ value only surfaced mid-restore
    (inside the node-creation loop), leaving a partial write behind
    despite this module's no-partial-restore guarantee -- found via the
    T033 restore rehearsal when a real Date-typed property (pre-dating
    the __temporal_type__ fix) crashed after 3 nodes had already been
    written to the scratch target."""
    bad_property = {"joined": {"__temporal__": "not-a-real-date"}}
    document = {
        "schema_version": "v1",
        "nodes": [{"key": "n1", "labels": ["User"], "properties": bad_property}],
        "relationships": [],
        "counts": {"nodes": {}, "relationships": {}},
    }
    driver = FakeDriver([])  # no results queued -- proves no query is ever run

    with pytest.raises(MalformedExport):
        await restore_graph(driver, document, force_empty_check_off=True)


async def test_unknown_relationship_type_rejected_before_any_write() -> None:
    document = {
        "schema_version": "v1",
        "nodes": [],
        "relationships": [
            {"type": "DROP_EVERYTHING", "start_key": "a", "end_key": "b", "properties": {}}
        ],
        "counts": {"nodes": {}, "relationships": {}},
    }
    driver = FakeDriver([])

    with pytest.raises(MalformedExport):
        await restore_graph(driver, document, force_empty_check_off=True)
