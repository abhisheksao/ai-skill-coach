"""Contract test 2: protected routes reject missing/garbage/expired/wrong-audience
tokens with the 401 error envelope, and accept a valid token."""

import pytest

from coach_core.errors import error_body

pytestmark = [pytest.mark.foundations, pytest.mark.auth]

UNAUTHORIZED = error_body("unauthorized", "errors.unauthorized")


def test_missing_token(client) -> None:
    response = client.get("/v1/_probe")
    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_garbage_token(client) -> None:
    response = client.get("/v1/_probe", headers={"Authorization": "Bearer not-a-jwt"})
    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_expired_token(client, make_token) -> None:
    token = make_token(expires_in=-60)
    response = client.get("/v1/_probe", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_wrong_audience(client, make_token) -> None:
    token = make_token(audience="somebody-else")
    response = client.get("/v1/_probe", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401
    assert response.json() == UNAUTHORIZED


def test_valid_token_extracts_sub(client, make_token) -> None:
    sub = "11111111-2222-3333-4444-555555555555"
    response = client.get("/v1/_probe", headers={"Authorization": f"Bearer {make_token(sub=sub)}"})
    assert response.status_code == 200
    assert response.json() == {"sub": sub}


def test_httpx_jwks_client_fetch_failure_maps_to_jwt_error(monkeypatch, make_token) -> None:
    """A JWKS outage must surface as a PyJWTError (→ 401), never a 500."""
    import httpx as httpx_module
    import jwt as jwt_module
    import pytest as pytest_module

    from skillcoach_api.auth import HttpxJwksClient

    def boom(*_args, **_kwargs):
        raise httpx_module.ConnectError("no network")

    monkeypatch.setattr(httpx_module, "get", boom)
    client = HttpxJwksClient("https://example.com/jwks.json")
    with pytest_module.raises(jwt_module.PyJWTError):
        client.get_signing_key_from_jwt(make_token())
