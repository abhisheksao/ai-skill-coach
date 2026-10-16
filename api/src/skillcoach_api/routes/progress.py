"""GET /v1/skills/{id}/progress (User Story 2) — computed on demand from
ProgressService every call (FR-004/Constitution II: no cached counter,
two calls in a row always agree). GET /v1/dashboard (User Story 6, Phase
7) composes the same ProgressService call per skill at coarser grain —
SC-006's "always agree" is a structural consequence of there being one
progress-derivation code path, not a separately tested guarantee.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request

from coach_core.errors import ApiError
from skillcoach_api import constants
from skillcoach_api.auth import RequirePrincipal
from skillcoach_api.models.progress import (
    DashboardResponse,
    DashboardSkillCard,
    DashboardSkillProgress,
    DashboardStepCard,
    SkillProgressResponse,
)

router = APIRouter()


def _as_aware_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@router.get("/v1/skills/{skill_id}/progress")
async def get_skill_progress(
    skill_id: str, principal: RequirePrincipal, request: Request
) -> SkillProgressResponse:
    services = request.app.state.services

    skill = await services.skills.get_skill(principal.sub, skill_id)
    if skill is None:
        # Never distinguish "doesn't exist" from "not yours" (Constitution I).
        raise ApiError(404, "not_found", "errors.not_found")

    timezone = await services.messages.profile_timezone(principal.sub)
    progress = await services.progress.compute(principal.sub, skill_id, timezone)
    return SkillProgressResponse.from_domain(progress)


@router.get("/v1/dashboard")
async def get_dashboard(principal: RequirePrincipal, request: Request) -> DashboardResponse:
    """User Story 6 (FR-014): one card per skill, composing
    `SkillsService.list_skills` with the exact same `ProgressService`
    call `GET /v1/skills/{id}/progress` uses. `is_stale`: no `CheckIn`
    anywhere under the skill within `constants.STALE_GOAL_DAYS`, or the
    skill's `created_at` if it has none yet (research.md R9). Also
    includes a per-step list (User Story 7, Phase 8) so the dashboard can
    render a tap-to-complete/log-partial affordance per step, not just an
    aggregate count — one extra `get_skill` call per skill for the step
    descriptions `list_skills` doesn't carry."""
    services = request.app.state.services

    summaries = await services.skills.list_skills(principal.sub)
    if not summaries:
        return DashboardResponse(skills=[])

    timezone = await services.messages.profile_timezone(principal.sub)
    now = datetime.now(UTC)
    stale_threshold = timedelta(days=constants.STALE_GOAL_DAYS)

    cards = []
    for summary in summaries:
        skill = await services.skills.get_skill(principal.sub, summary.id)
        if skill is None:
            continue  # scoped identically to list_skills; shouldn't happen

        progress = await services.progress.compute(principal.sub, summary.id, timezone)
        progress_by_order = {s.order: s for s in progress.steps}

        checkin_times = [s.last_checkin_at for s in progress.steps if s.last_checkin_at]
        last_activity = max(checkin_times) if checkin_times else summary.created_at
        is_stale = (now - _as_aware_utc(last_activity)) > stale_threshold

        cards.append(
            DashboardSkillCard(
                skill_id=summary.id,
                name=summary.name,
                goal_statement=summary.goal_statement,
                target_date=summary.target_date,
                is_stale=is_stale,
                progress=DashboardSkillProgress(
                    completed_steps=len(progress.completed_steps),
                    total_steps=progress.total_steps,
                    streak_days=progress.streak_days,
                ),
                steps=[
                    DashboardStepCard(
                        order=step.order,
                        description=step.description,
                        # .get(), not [] -- defensive against the two reads
                        # (get_skill, progress.compute) racing a concurrent
                        # revise_plan between them; a step with no progress
                        # row yet just isn't completed/behind.
                        completed=(
                            progress_by_order[step.order].completed
                            if step.order in progress_by_order
                            else False
                        ),
                        behind_cadence=(
                            progress_by_order[step.order].behind_cadence
                            if step.order in progress_by_order
                            else False
                        ),
                    )
                    for step in skill.plan.steps
                ],
            )
        )

    return DashboardResponse(skills=cards)
