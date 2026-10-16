"""Contract tests 3–4 for POST /v1/profile (contracts/api.md)."""

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from coach_core.errors import error_body
from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from tests.fakes import FakeGraph, FakeJwksClient, FakeProfiles

pytestmark = [pytest.mark.foundations, pytest.mark.profile]

VALID_BODY = {
    "display_name": "Abhi",
    "language": "hi",
    "timezone": "Asia/Kolkata",
    "consent": True,
}


@pytest.fixture
def profile_app(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    app = create_app()
    fakes = SimpleNamespace(profiles=FakeProfiles(), graph=FakeGraph())
    app.state.services = fakes
    return TestClient(app, raise_server_exceptions=False), fakes


def _post(client, token, body=None):
    return client.post(
        "/v1/profile", json=body or VALID_BODY, headers={"Authorization": f"Bearer {token}"}
    )


def test_contract_3_create_then_repeat_is_idempotent(profile_app, make_token) -> None:
    client, fakes = profile_app
    token = make_token(sub="user-1")

    first = _post(client, token)
    assert first.status_code == 200
    profile = first.json()["profile"]
    assert profile["display_name"] == "Abhi"
    assert profile["language"] == "hi"
    assert profile["timezone"] == "Asia/Kolkata"
    assert profile["consent_at"]

    second = _post(client, token)
    assert second.status_code == 200

    # Upsert both times, same user; graph MERGE attempted both times.
    assert [u["user_id"] for u in fakes.profiles.upserts] == ["user-1", "user-1"]
    assert fakes.graph.calls == ["user-1", "user-1"]


def test_contract_4_consent_false_rejected(profile_app, make_token) -> None:
    client, fakes = profile_app
    response = _post(client, make_token(), {**VALID_BODY, "consent": False})
    assert response.status_code == 422
    assert response.json() == error_body("validation_error", "errors.validation")
    assert fakes.profiles.upserts == []


@pytest.mark.parametrize(
    "override",
    [{"language": "pt"}, {"timezone": "Not/AZone"}, {"display_name": ""}],
)
def test_invalid_fields_rejected(profile_app, make_token, override) -> None:
    client, _ = profile_app
    response = _post(client, make_token(), {**VALID_BODY, **override})
    assert response.status_code == 422


def test_graph_failure_still_returns_200(profile_app, make_token) -> None:
    client, fakes = profile_app
    fakes.graph.healthy = False
    response = _post(client, make_token(sub="user-2"))
    assert response.status_code == 200  # /chat reconciliation heals later
    assert [u["user_id"] for u in fakes.profiles.upserts] == ["user-2"]


@pytest.mark.voice_layer
def test_voice_replies_enabled_defaults_to_true(profile_app, make_token) -> None:
    """003 T017 (FR-004): omitting voice_replies_enabled defaults to true."""
    client, _ = profile_app
    response = _post(client, make_token(sub="user-1"))
    assert response.status_code == 200
    assert response.json()["profile"]["voice_replies_enabled"] is True


@pytest.mark.voice_layer
def test_voice_replies_enabled_false_persists(profile_app, make_token) -> None:
    """003 T017: an explicit false round-trips through the upsert."""
    client, fakes = profile_app
    response = _post(
        client, make_token(sub="user-1"), {**VALID_BODY, "voice_replies_enabled": False}
    )
    assert response.status_code == 200
    assert response.json()["profile"]["voice_replies_enabled"] is False
    assert fakes.profiles.upserts[0]["voice_replies_enabled"] is False


def test_requires_auth(profile_app) -> None:
    client, _ = profile_app
    assert client.post("/v1/profile", json=VALID_BODY).status_code == 401
