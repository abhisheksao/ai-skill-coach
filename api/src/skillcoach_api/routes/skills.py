"""GET /v1/skills, GET /v1/skills/{id} — list cards + detail (User Story 3;
list also drives FR-012's client-side duplicate-name check and detail
drives the plan review screen — both pulled forward from Phase 2 since the
wizard-completion flow needed them). POST .../plan/regenerate (User Story
2, FR-011) — capped at 3 user-visible attempts, derived from the Plan's
SUPERSEDES chain depth (research R5), with a similarity-guarded internal
retry (research R6) before applying.
"""

from fastapi import APIRouter, Request

from coach_core.errors import ApiError
from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.models.intents import RevisePlanIntent
from skillcoach_api.models.skills import (
    RegenerateRequest,
    RegenerateResponse,
    SkillDetail,
    SkillsListResponse,
)
from skillcoach_api.services.context_builder import ConversationContext
from skillcoach_api.services.plan_similarity import is_materially_similar

router = APIRouter()

MAX_REGENERATIONS = 3


@router.get("/v1/skills")
async def list_skills(principal: RequirePrincipal, request: Request) -> SkillsListResponse:
    services = request.app.state.services
    skills = await services.skills.list_skills(principal.sub)
    return SkillsListResponse(skills=skills)


@router.get("/v1/skills/{skill_id}")
async def get_skill(skill_id: str, principal: RequirePrincipal, request: Request) -> SkillDetail:
    services = request.app.state.services
    detail = await services.skills.get_skill(principal.sub, skill_id)
    if detail is None:
        # Never distinguish "doesn't exist" from "not yours" (Constitution I).
        raise ApiError(404, "not_found", "errors.not_found")
    return detail


@router.post("/v1/skills/{skill_id}/plan/regenerate")
async def regenerate_plan(
    skill_id: str, body: RegenerateRequest, principal: RequirePrincipal, request: Request
) -> RegenerateResponse:
    services = request.app.state.services

    skill = await services.skills.get_skill(principal.sub, skill_id)
    if skill is None:
        raise ApiError(404, "not_found", "errors.not_found")

    if skill.plan.generation >= MAX_REGENERATIONS:
        # No LLM call at the cap (contracts/api.md) — the client routes the
        # user back into the wizard to revise the underlying facts (T018).
        raise ApiError(409, "regeneration_cap_reached", "errors.regeneration_cap_reached")

    await services.budget.acquire(principal.sub)

    language = await services.messages.profile_language(principal.sub)
    context = ConversationContext(
        language=language, skill=skill, recent_messages=[], user_turn_count=0
    )

    turn, usage = await services.llm.generate_regeneration(context, body.reason, body.note)

    new_steps = next(
        (intent.steps for intent in turn.intents if isinstance(intent, RevisePlanIntent)), None
    )
    if new_steps and is_materially_similar(skill.plan.steps, new_steps):
        # Transparent, uncounted retry (research R6) — not a user-visible attempt.
        turn, usage = await services.llm.generate_regeneration(
            context, body.reason, body.note, force_different=True
        )
    await services.budget.report(principal.sub, usage)

    if turn.intents:
        await services.intent_apply.apply_intents(turn.intents, principal.sub, skill_id=skill_id)
        # Regenerate always emits a revise_plan (research.md) -- keep the
        # cadence_schedules projection in sync here too, same reasoning as
        # routes/chat.py's revise_plan branch (FR-008 must hold regardless
        # of which endpoint revised the plan). Recomputed from the FINAL
        # turn.intents, not the pre-retry `new_steps` above -- a
        # force_different retry reassigns `turn`, and syncing the
        # discarded near-duplicate attempt's steps would be wrong.
        applied_steps = next(
            (i.steps for i in turn.intents if isinstance(i, RevisePlanIntent)), None
        )
        if applied_steps is not None:
            await services.cadence_schedule.sync(principal.sub, skill_id, applied_steps)

    updated = await services.skills.get_skill(principal.sub, skill_id)
    return RegenerateResponse(reply=turn.reply, plan=updated.plan if updated else skill.plan)
