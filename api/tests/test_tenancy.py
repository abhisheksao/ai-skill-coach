"""Contract test 8 (T031): tenant isolation — Constitution I.

The API derives identity exclusively from the verified JWT `sub`. A client
can never write rows or nodes for another user by manipulating the request
body, and two tokens produce strictly disjoint writes. (Read isolation is
enforced by RLS policies in the migration: clients select only
`user_id = auth.uid()`, and have no write grants at all.)
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from skillcoach_api import auth as auth_module
from skillcoach_api.main import create_app
from tests.fakes import (
    FakeAnalytics,
    FakeBudget,
    FakeContextBuilder,
    FakeGraph,
    FakeIntentApply,
    FakeJwksClient,
    FakeLlm,
    FakeMessages,
    FakeProfiles,
)

pytestmark = [pytest.mark.foundations, pytest.mark.tenancy]

USER_A = "aaaaaaaa-0000-0000-0000-000000000001"
USER_B = "bbbbbbbb-0000-0000-0000-000000000002"
SESSION_ID = str(uuid.uuid4())


@pytest.fixture
def app_with_fakes(rsa_key, monkeypatch):
    monkeypatch.setattr(
        auth_module, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key())
    )
    app = create_app()
    fakes = SimpleNamespace(
        budget=FakeBudget(),
        llm=FakeLlm(reply="ok"),
        messages=FakeMessages(),
        profiles=FakeProfiles(),
        graph=FakeGraph(),
        context_builder=FakeContextBuilder(),
        intent_apply=FakeIntentApply(),
        analytics=FakeAnalytics(),
    )
    app.state.services = fakes
    return TestClient(app, raise_server_exceptions=False), fakes


def test_chat_identity_comes_from_token_not_body(app_with_fakes, make_token) -> None:
    client, fakes = app_with_fakes
    # Malicious body smuggles user identifiers; pydantic must ignore them.
    client.post(
        "/v1/chat",
        json={
            "message": "hi",
            "session_id": SESSION_ID,
            "user_id": USER_B,
            "sub": USER_B,
        },
        headers={"Authorization": f"Bearer {make_token(sub=USER_A)}"},
    )
    assert fakes.messages.inserted[0]["user_id"] == USER_A
    assert fakes.budget.calls == [USER_A]
    assert fakes.graph.calls == [USER_A]


def test_profile_identity_comes_from_token_not_body(app_with_fakes, make_token) -> None:
    client, fakes = app_with_fakes
    client.post(
        "/v1/profile",
        json={
            "language": "en",
            "timezone": "Asia/Kolkata",
            "consent": True,
            "user_id": USER_B,  # smuggled; must be ignored
        },
        headers={"Authorization": f"Bearer {make_token(sub=USER_A)}"},
    )
    assert fakes.profiles.upserts[0]["user_id"] == USER_A
    assert fakes.graph.calls == [USER_A]


def test_two_tokens_produce_disjoint_writes(app_with_fakes, make_token) -> None:
    client, fakes = app_with_fakes
    for sub in (USER_A, USER_B):
        client.post(
            "/v1/chat",
            json={"message": "hi", "session_id": SESSION_ID},
            headers={"Authorization": f"Bearer {make_token(sub=sub)}"},
        )
    assert [row["user_id"] for row in fakes.messages.inserted] == [USER_A, USER_B]
    assert fakes.budget.calls == [USER_A, USER_B]


def test_migration_grants_no_client_writes() -> None:
    """The migration must never add client write policies or broad grants."""
    from pathlib import Path

    migration = (
        Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260712000001_init.sql"
    )
    sql = migration.read_text().lower()
    for forbidden in ("for insert", "for update", "for delete", "for all"):
        assert forbidden not in sql, f"client write policy found: {forbidden}"
    assert sql.count("for select") == 2  # profiles + messages select-own only
