"""POST /v1/intents/apply (User Story 7, FR-015/FR-016) — the UI-native
tap-to-complete/log-partial path. Validates against the exact same
Pydantic schemas and applies through the exact same `IntentApplyService`
as a conversational intent (Constitution I, Amendment 1.5.0) — the LLM
call is the only thing skipped here, never validation or the translator.
No budget/LLM call happens on this path at all (SC-007).

`source` is never read from the request body — it's hardcoded here to
`"ui_tap"`, so a client cannot masquerade a tap as conversational
provenance (FR-016). A Pydantic validation failure (e.g. an unknown
`intent.type`) surfaces via FastAPI's standard 422 handler (main.py) with
no retry (FR-015) — there is no LLM feedback-retry loop on this path to
fall back to.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from coach_core.errors import ApiError
from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.models.checkins import ApplyIntentRequest, ApplyIntentResponse

router = APIRouter()


@router.post("/v1/intents/apply")
async def apply_intent(
    body: ApplyIntentRequest, principal: RequirePrincipal, request: Request
) -> ApplyIntentResponse:
    services = request.app.state.services

    skill = await services.skills.get_skill(principal.sub, body.skill_id)
    if skill is None:
        raise ApiError(404, "not_found", "errors.not_found")

    valid_step_orders = {step.order for step in skill.plan.steps}
    result = await services.intent_apply.apply_intents(
        [body.intent],
        principal.sub,
        skill_id=body.skill_id,
        valid_step_orders=valid_step_orders,
        source="ui_tap",
    )

    return ApplyIntentResponse(checkin_id=result.checkin_id, applied_at=datetime.now(UTC))
