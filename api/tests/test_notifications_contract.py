"""POST/DELETE /v1/push-tokens (FR-013) and the shared-secret auth guard
on the internal cron-triggered routes (004, research.md R1)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api import internal_auth as internal_auth_module
from skillcoach_api.main import create_app
from tests.fakes import FakeJwksClient

pytestmark = [pytest.mark.progress_notifications, pytest.mark.notifications]


class FakeNotifications:
    def __init__(self) -> None:
        self.registered: list[tuple] = []
        self.revoked: list[tuple] = []

    async def register_token(self, user_id: str, token: str, platform: str) -> None:
        self.registered.append((user_id, token, platform))

    async def revoke_token(self, user_id: str, token: str) -> None:
        self.revoked.append((user_id, token))


@pytest.fixture
def notifications_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    app = create_app()
    fake = FakeNotifications()
    app.state.services = SimpleNamespace(notifications=fake)
    return app, fake


def test_register_push_token_calls_service_and_returns_204(notifications_app, make_token) -> None:
    app, fake = notifications_app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.post(
        "/v1/push-tokens",
        json={"token": "ExponentPushToken[abc]", "platform": "ios"},
        headers={"Authorization": f"Bearer {make_token(sub='user-1')}"},
    )

    assert response.status_code == 204
    assert fake.registered == [("user-1", "ExponentPushToken[abc]", "ios")]


def test_re_registering_covers_platform_rotation_no_separate_endpoint(
    notifications_app, make_token
) -> None:
    """FR-013's "refreshed when the platform rotates them" -- re-calling
    the same register endpoint with the new token is the whole mechanism,
    no dedicated "refresh" route exists (upsert-on-conflict on the DB
    side, tested directly in test_notifications.py)."""
    app, fake = notifications_app
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"Authorization": f"Bearer {make_token(sub='user-1')}"}

    r1 = client.post(
        "/v1/push-tokens", json={"token": "old-token", "platform": "ios"}, headers=headers
    )
    r2 = client.post(
        "/v1/push-tokens", json={"token": "new-token", "platform": "ios"}, headers=headers
    )

    assert r1.status_code == 204
    assert r2.status_code == 204
    assert [t for _, t, _ in fake.registered] == ["old-token", "new-token"]


def test_revoke_push_token_calls_service_and_returns_204(notifications_app, make_token) -> None:
    app, fake = notifications_app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.request(
        "DELETE",
        "/v1/push-tokens",
        json={"token": "ExponentPushToken[abc]"},
        headers={"Authorization": f"Bearer {make_token(sub='user-1')}"},
    )

    assert response.status_code == 204
    assert fake.revoked == [("user-1", "ExponentPushToken[abc]")]


def test_revoke_is_idempotent_for_an_unknown_token(notifications_app, make_token) -> None:
    app, _ = notifications_app
    client = TestClient(app, raise_server_exceptions=False)

    response = client.request(
        "DELETE",
        "/v1/push-tokens",
        json={"token": "never-registered"},
        headers={"Authorization": f"Bearer {make_token(sub='user-1')}"},
    )

    assert response.status_code == 204


def test_register_push_token_requires_auth(notifications_app) -> None:
    app, _ = notifications_app
    client = TestClient(app, raise_server_exceptions=False)
    response = client.post("/v1/push-tokens", json={"token": "t", "platform": "ios"})
    assert response.status_code == 401


# ---------------------------------------------------- internal-secret auth


@pytest.fixture
def internal_app(monkeypatch):
    monkeypatch.setattr(
        internal_auth_module, "get_settings", lambda: SimpleNamespace(internal_secret="test-secret")
    )
    return create_app()


def test_scan_notifications_rejects_missing_secret_header(internal_app) -> None:
    client = TestClient(internal_app, raise_server_exceptions=False)
    response = client.post("/v1/internal/notifications/scan")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_scan_notifications_rejects_wrong_secret_header(internal_app) -> None:
    client = TestClient(internal_app, raise_server_exceptions=False)
    response = client.post(
        "/v1/internal/notifications/scan", headers={"X-Internal-Secret": "wrong"}
    )

    assert response.status_code == 401


def test_scan_notifications_accepts_the_correct_secret_header(internal_app) -> None:
    """Reaches the real route body -- app.state.services is the real,
    unconfigured container (no Neo4j/Supabase creds), so cadence_schedule
    reads against a real (but unreachable) SupabaseRest and would raise;
    this only proves the AUTH gate passes through, not the scan's business
    logic (that's routes/internal.py's own dedicated tests)."""
    client = TestClient(internal_app, raise_server_exceptions=False)
    response = client.post(
        "/v1/internal/notifications/scan", headers={"X-Internal-Secret": "test-secret"}
    )

    assert response.status_code != 401


def test_summarize_sessions_rejects_missing_secret_header(internal_app) -> None:
    client = TestClient(internal_app, raise_server_exceptions=False)
    response = client.post("/v1/internal/sessions/summarize")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_summarize_sessions_rejects_wrong_secret_header(internal_app) -> None:
    client = TestClient(internal_app, raise_server_exceptions=False)
    response = client.post(
        "/v1/internal/sessions/summarize", headers={"X-Internal-Secret": "wrong"}
    )

    assert response.status_code == 401


def test_summarize_sessions_accepts_the_correct_secret_header(internal_app) -> None:
    client = TestClient(internal_app, raise_server_exceptions=False)
    response = client.post(
        "/v1/internal/sessions/summarize", headers={"X-Internal-Secret": "test-secret"}
    )

    assert response.status_code != 401
