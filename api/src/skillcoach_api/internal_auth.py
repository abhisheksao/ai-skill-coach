"""Shared-secret auth for the two internal cron-triggered endpoints
(004, research.md R1) — there's no authenticated user for a pg_cron/
pg_net trigger, so this mirrors auth.py's RequirePrincipal shape but
checks a header against Settings.internal_secret instead of decoding a
JWT.
"""

from typing import Annotated

from fastapi import Depends, Header

from coach_core.errors import Unauthorized
from skillcoach_api.config import get_settings


async def require_internal_secret(
    x_internal_secret: Annotated[str | None, Header()] = None,
) -> None:
    settings = get_settings()
    # Fails closed: an unconfigured (empty) secret never matches any
    # header value, including another empty/missing one.
    if not settings.internal_secret or x_internal_secret != settings.internal_secret:
        raise Unauthorized()


RequireInternalSecret = Annotated[None, Depends(require_internal_secret)]
