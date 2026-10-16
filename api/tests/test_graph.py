"""GraphService: parameterized idempotent MERGE; failures never raise."""

import pytest

from skillcoach_api.services.graph import GraphService

pytestmark = [pytest.mark.foundations, pytest.mark.graph]


class FakeSession:
    def __init__(self, log: list, fail: bool) -> None:
        self._log = log
        self._fail = fail

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def run(self, query: str, **params):
        if self._fail:
            raise RuntimeError("aura paused")
        self._log.append((query, params))


class FakeDriver:
    def __init__(self, fail: bool = False) -> None:
        self.log: list = []
        self._fail = fail

    def session(self) -> FakeSession:
        return FakeSession(self.log, self._fail)


async def test_ensure_user_merges_parameterized() -> None:
    driver = FakeDriver()
    service = GraphService(driver)
    assert await service.ensure_user("user-1") is True

    query, params = driver.log[0]
    assert "MERGE (u:User {id: $id})" in query
    assert params == {"id": "user-1"}
    assert "user-1" not in query  # parameterized, never interpolated


async def test_failure_returns_false_never_raises() -> None:
    service = GraphService(FakeDriver(fail=True))
    assert await service.ensure_user("user-1") is False


async def test_unconfigured_skips() -> None:
    assert await GraphService(None).ensure_user("user-1") is False


def test_from_settings_downgrades_plus_s_to_certifi_trust(monkeypatch) -> None:
    """neo4j+s:// must become neo4j:// + encrypted + certifi CAs (macOS
    installs without system certs otherwise fail TLS inside the driver)."""
    from types import SimpleNamespace

    import neo4j

    captured = {}

    def fake_driver(uri, auth=None, **kwargs):
        captured["uri"] = uri
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(neo4j.AsyncGraphDatabase, "driver", staticmethod(fake_driver))
    settings = SimpleNamespace(
        neo4j_uri="neo4j+s://abc123.databases.neo4j.io",
        neo4j_user="neo4j",
        neo4j_password="secret",
    )
    GraphService.from_settings(settings)

    assert captured["uri"] == "neo4j://abc123.databases.neo4j.io"
    assert captured["kwargs"]["encrypted"] is True
    assert type(captured["kwargs"]["trusted_certificates"]).__name__ == "TrustCustomCAs"
