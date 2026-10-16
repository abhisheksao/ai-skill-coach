"""Request authentication: the FastAPI dependency around coach_core.auth.

The verified `sub` claim is the request principal; every downstream
read/write is scoped to it (Constitution I).
"""

from typing import Annotated

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from coach_core.auth import HttpxJwksClient, Principal, decode_token, jwks_client
from coach_core.errors import Unauthorized
from skillcoach_api.config import get_settings

__all__ = ["HttpxJwksClient", "Principal", "RequirePrincipal", "current_principal"]

_bearer = HTTPBearer(auto_error=False)

# Module-level seam: tests swap this for a fake JWKS client.
_jwks_client = jwks_client


def _decode(token: str) -> dict:
    settings = get_settings()
    return decode_token(token, _jwks_client(settings.supabase_jwks_url))


async def current_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None or not credentials.credentials:
        raise Unauthorized()
    try:
        claims = _decode(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise Unauthorized() from exc
    sub = str(claims["sub"])
    request.state.sub = sub  # for the request log line (T032); never the token
    return Principal(sub=sub, claims=claims)


RequirePrincipal = Annotated[Principal, Depends(current_principal)]
