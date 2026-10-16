"""AnalyticsService: fire-and-forget event writes (005, research.md R8)."""

import pytest

from coach_core.analytics import AnalyticsService

pytestmark = [pytest.mark.hardening, pytest.mark.analytics]


class FakeRest:
    def __init__(self, fail: Exception | None = None) -> None:
        self.fail = fail
        self.inserted: list[tuple[str, list[dict]]] = []

    async def insert(self, table: str, rows: list[dict]) -> None:
        if self.fail:
            raise self.fail
        self.inserted.append((table, rows))


async def test_emit_inserts_event_row() -> None:
    rest = FakeRest()
    service = AnalyticsService(rest)

    await service.emit("session_started", "user-1", {"skill_id": "skill-1"})

    assert rest.inserted == [
        (
            "analytics_events",
            [
                {
                    "event_type": "session_started",
                    "user_sub": "user-1",
                    "properties": {"skill_id": "skill-1"},
                }
            ],
        )
    ]


async def test_emit_defaults_properties_to_empty_dict() -> None:
    rest = FakeRest()
    service = AnalyticsService(rest)

    await service.emit("session_ended", "user-1")

    assert rest.inserted[0][1][0]["properties"] == {}


async def test_emit_failure_is_swallowed_never_raises() -> None:
    rest = FakeRest(fail=RuntimeError("PostgREST unreachable"))
    service = AnalyticsService(rest)

    await service.emit("push_sent", "user-1")  # must not raise


async def test_emit_properties_never_carry_a_message_body_key() -> None:
    """FR-007: analytics properties must never smuggle transcript content --
    negative-case guard so a future call site can't accidentally pass one."""
    rest = FakeRest()
    service = AnalyticsService(rest)

    await service.emit(
        "intent_validation_failed", "user-1", {"endpoint": "/v1/chat", "attempts": 3}
    )

    properties = rest.inserted[0][1][0]["properties"]
    for forbidden_key in ("message", "content", "reply", "transcript", "body"):
        assert forbidden_key not in properties
