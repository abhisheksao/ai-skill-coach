"""POST /v1/profile — completes the post-signup profile step (FR-006).

Order: profiles row first (transactional source of truth), then the graph
MERGE. A graph failure still returns 200 — the /chat reconciliation path
heals it (spec US3 scenario 2)."""

from fastapi import APIRouter, Request

from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.models.profile import ProfileRequest, ProfileResponse

router = APIRouter()

_PROFILE_FIELDS = (
    "display_name",
    "language",
    "timezone",
    "consent_at",
    "voice_replies_enabled",
)


@router.post("/v1/profile")
async def upsert_profile(
    body: ProfileRequest, principal: RequirePrincipal, request: Request
) -> ProfileResponse:
    services = request.app.state.services

    row = await services.profiles.upsert(
        user_id=principal.sub,
        display_name=body.display_name,
        language=body.language,
        timezone=body.timezone,
        voice_replies_enabled=body.voice_replies_enabled,
    )

    # Best-effort graph write; failure is healed lazily by /chat.
    await services.graph.ensure_user(principal.sub)

    return ProfileResponse(profile={k: row.get(k) for k in _PROFILE_FIELDS})
