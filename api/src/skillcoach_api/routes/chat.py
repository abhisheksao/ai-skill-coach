"""POST /v1/chat — the single message pipeline (Constitution IV).

Order: reconcile user -> budget -> context -> LLM -> apply intents ->
persist -> respond. On budget or LLM failure nothing is persisted
(FR-007: the client keeps the draft and retries; no phantom rows).
"""

from fastapi import APIRouter, Request

from coach_core.analytics import INTENT_VALIDATION_FAILED, SESSION_STARTED
from coach_core.errors import BudgetExceeded, LlmUnavailable
from coach_core.logging_setup import log_ai_failure
from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.models.chat import BudgetStatus, ChatRequest, ChatResponse
from skillcoach_api.models.intents import CreatePlanIntent, RevisePlanIntent

router = APIRouter()

_BUDGET_EXHAUSTED_REPLY_KEY = "errors.budget_exhausted_reply"
_DEGRADED_VALIDATION_REPLY_KEY = "errors.validation"
# FR-006's own retry cap (llm.py's _MAX_VALIDATION_ATTEMPTS): 1 initial +
# 2 feedback retries. The degraded turn is only ever reached after all 3.
_VALIDATION_ATTEMPTS_ON_DEGRADE = 3


@router.post("/v1/chat")
async def chat(body: ChatRequest, principal: RequirePrincipal, request: Request) -> ChatResponse:
    services = request.app.state.services

    # Lazy reconciliation (T029/FR-006): heals a missing (:User) node, e.g.
    # when Aura was paused during the profile step.
    await services.graph.ensure_user(principal.sub)

    skill_id = str(body.skill_id) if body.skill_id else None

    try:
        await services.budget.acquire(principal.sub)
    except BudgetExceeded as exc:
        # 005, contracts/api.md R2: budget exhaustion (or the user_limits
        # kill switch -- indistinguishable here, resets_at just omitted)
        # becomes an in-conversation coach turn, not a raw error. Zero LLM
        # calls; persisted the same way the degraded-validation turn is so
        # the transcript stays honest about what the user actually saw.
        await services.messages.insert_turn(
            user_id=principal.sub,
            session_id=str(body.session_id),
            skill_id=skill_id,
            user_text=body.message,
            assistant_text=_BUDGET_EXHAUSTED_REPLY_KEY,
            modality=body.modality,
        )
        return ChatResponse(
            reply=_BUDGET_EXHAUSTED_REPLY_KEY,
            session_id=body.session_id,
            skill_id=skill_id,
            intents=[],
            suggested_replies=[],
            budget=BudgetStatus(exhausted=True, resets_at=exc.resets_at),
        )

    context = await services.context_builder.build(principal.sub, skill_id, str(body.session_id))
    if context.user_turn_count == 0:
        # 005, research.md R8: session boundary -- the FIRST user message
        # in this session, before this turn's own insert_turn below.
        await services.analytics.emit(SESSION_STARTED, principal.sub, {"skill_id": skill_id})

    intent_type = "wizard" if skill_id is None else "coaching"
    try:
        if skill_id is None:
            turn, usage = await services.llm.generate_wizard_turn(
                body.message, body.new_skill_name, context
            )
        else:
            turn, usage = await services.llm.generate_coaching_turn(body.message, context)
    except LlmUnavailable as exc:
        # 005, research.md R14 -- "the llm/chat seam": chat.py is where
        # endpoint + sub + intent type are all known at once; llm.py
        # itself is deliberately request-context-free (injectable,
        # tested with a bare fake runnable), so this seam is where the
        # structured event belongs, not deeper inside llm.py.
        log_ai_failure("/v1/chat", principal.sub, intent_type, type(exc).__name__)
        raise
    await services.budget.report(principal.sub, usage)

    if turn.reply == _DEGRADED_VALIDATION_REPLY_KEY:
        log_ai_failure("/v1/chat", principal.sub, intent_type, "validation_exhausted")
        await services.analytics.emit(
            INTENT_VALIDATION_FAILED,
            principal.sub,
            {"endpoint": "/v1/chat", "attempts": _VALIDATION_ATTEMPTS_ON_DEGRADE},
        )

    resolved_skill_id = skill_id
    if turn.intents:
        # skill_id here is the caller's already-resolved skill (None during
        # a brand-new wizard) -- revise_plan/revise_goal need it to target
        # the right skill by id, never by a name the LLM might mis-echo
        # (intent_apply.py's module docstring has the full rationale).
        # valid_step_orders guards the three check-in intents (004) against
        # a step_order outside the plan already loaded into context --
        # no extra graph round-trip, ContextBuilder already fetched it.
        valid_step_orders = {s.order for s in context.skill.plan.steps} if context.skill else None
        result = await services.intent_apply.apply_intents(
            turn.intents, principal.sub, skill_id=skill_id, valid_step_orders=valid_step_orders
        )
        if result.created_skill_id:
            resolved_skill_id = result.created_skill_id

        # A create_plan/revise_plan batch (re)defines the plan's steps --
        # keep the flat cadence_schedules projection (004, research.md R8)
        # in sync so the nightly notification scan never reads a stale
        # cadence for this skill.
        plan_steps = next(
            (i.steps for i in turn.intents if isinstance(i, CreatePlanIntent | RevisePlanIntent)),
            None,
        )
        if plan_steps is not None:
            await services.cadence_schedule.sync(principal.sub, resolved_skill_id, plan_steps)

    await services.messages.insert_turn(
        user_id=principal.sub,
        session_id=str(body.session_id),
        skill_id=resolved_skill_id,
        user_text=body.message,
        assistant_text=turn.reply,
        modality=body.modality,
    )

    return ChatResponse(
        reply=turn.reply,
        session_id=body.session_id,
        skill_id=resolved_skill_id,
        intents=turn.intents,
        suggested_replies=turn.suggested_replies,
    )
