"""Shared fixtures: app with a protected probe route, RSA keypair, token factory."""

import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import APIRouter
from fastapi.testclient import TestClient

from skillcoach_api import auth
from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.main import create_app
from tests.fakes import FakeJwksClient


@pytest.fixture(scope="session")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def client(rsa_key, monkeypatch) -> TestClient:
    monkeypatch.setattr(auth, "_jwks_client", lambda _url: FakeJwksClient(rsa_key.public_key()))
    app = create_app()

    probe = APIRouter()

    @probe.get("/v1/_probe")
    async def probe_route(principal: RequirePrincipal) -> dict:
        return {"sub": principal.sub}

    app.include_router(probe)
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def make_token(rsa_key):
    def _make(
        sub: str = "00000000-0000-0000-0000-000000000001",
        expires_in: int = 3600,
        audience: str = "authenticated",
    ) -> str:
        now = int(time.time())
        claims = {"sub": sub, "aud": audience, "iat": now, "exp": now + expires_in}
        return jwt.encode(claims, rsa_key, algorithm="RS256")

    return _make
