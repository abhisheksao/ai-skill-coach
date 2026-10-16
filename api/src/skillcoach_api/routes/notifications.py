"""POST/DELETE /v1/push-tokens (004, FR-013) — managed push-token
lifecycle, scoped to the calling user via the verified JWT.
"""

from fastapi import APIRouter, Request, Response

from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.models.notifications import RegisterPushTokenRequest, RevokePushTokenRequest

router = APIRouter()


@router.post("/v1/push-tokens", status_code=204)
async def register_push_token(
    body: RegisterPushTokenRequest, principal: RequirePrincipal, request: Request
) -> Response:
    services = request.app.state.services
    await services.notifications.register_token(principal.sub, body.token, body.platform)
    return Response(status_code=204)


@router.delete("/v1/push-tokens", status_code=204)
async def revoke_push_token(
    body: RevokePushTokenRequest, principal: RequirePrincipal, request: Request
) -> Response:
    services = request.app.state.services
    await services.notifications.revoke_token(principal.sub, body.token)
    return Response(status_code=204)
