"""Supabase JWT verification (research R4).

Tokens are verified against the project's JWKS endpoint. The verified `sub`
claim is the request principal; every downstream read/write is scoped to it
(Constitution I). The FastAPI dependency that reads the JWKS URL from
settings lives in the host app; this module holds the settings-free parts.
"""

import time
from dataclasses import dataclass
from functools import lru_cache

import jwt

_ALGORITHMS = ["ES256", "RS256"]
_AUDIENCE = "authenticated"


@dataclass(frozen=True)
class Principal:
    sub: str
    claims: dict


class HttpxJwksClient:
    """JWKS fetch via httpx (bundled CA certs) instead of PyJWKClient's
    urllib, which fails on Pythons without system certificates wired up.
    Same seam as PyJWKClient: get_signing_key_from_jwt(token)."""

    def __init__(self, jwks_url: str, lifespan: int = 900) -> None:
        self._jwks_url = jwks_url
        self._lifespan = lifespan
        self._by_kid: dict[str, jwt.PyJWK] = {}
        self._fetched_at = 0.0

    def _refresh(self) -> None:
        import httpx

        try:
            response = httpx.get(self._jwks_url, timeout=10)
            response.raise_for_status()
            keys = response.json().get("keys", [])
        except Exception as exc:
            raise jwt.PyJWTError(f"JWKS fetch failed: {type(exc).__name__}") from exc
        self._by_kid = {k["kid"]: jwt.PyJWK(k) for k in keys if "kid" in k}
        self._fetched_at = time.time()

    def get_signing_key_from_jwt(self, token: str) -> jwt.PyJWK:
        kid = jwt.get_unverified_header(token).get("kid")
        stale = time.time() - self._fetched_at > self._lifespan
        if stale or kid not in self._by_kid:
            self._refresh()
        if kid not in self._by_kid:
            raise jwt.PyJWTError("token kid not present in JWKS")
        return self._by_kid[kid]


@lru_cache
def jwks_client(jwks_url: str) -> HttpxJwksClient:
    return HttpxJwksClient(jwks_url)


def decode_token(token: str, jwks) -> dict:
    """Verify signature + expiry + audience; return claims. Raises on failure.
    `jwks` is anything with get_signing_key_from_jwt (HttpxJwksClient)."""
    signing_key = jwks.get_signing_key_from_jwt(token)
    return jwt.decode(
        token,
        signing_key.key,
        algorithms=_ALGORITHMS,
        audience=_AUDIENCE,
        options={"require": ["exp", "sub"]},
    )
