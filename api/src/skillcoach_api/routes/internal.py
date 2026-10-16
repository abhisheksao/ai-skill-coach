"""Internal, shared-secret-authenticated endpoints for the pg_cron/pg_net-
triggered jobs (004, research.md R1/R2) — never reachable from the app,
no user JWT involved (internal_auth.RequireInternalSecret instead).
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from skillcoach_api.internal_auth import RequireInternalSecret
from skillcoach_api.models.internal import NotificationScanResponse, SessionSummarizeResponse

router = APIRouter()


@router.post("/v1/internal/notifications/scan")
async def scan_notifications(
    request: Request, _secret: RequireInternalSecret
) -> NotificationScanResponse:
    """Fan out from `cadence_schedules` (flat SQL, research.md R8) to a
    per-skill behind-cadence check reusing `ProgressService` (research.md
    R7 — the exact same formula the progress view uses, so they can never
    disagree about what "behind" means), then gate/send/log through
    `NotificationsService` (frequency cap + quiet hours + delivery
    logging happen there, not here)."""
    services = request.app.state.services

    rows = await services.cadence_schedule.all_rows()
    candidates = {(row["user_id"], row["skill_id"]) for row in rows}

    now = datetime.now(UTC)
    scanned = notified = skipped = 0

    for user_id, skill_id in candidates:
        scanned += 1
        skill = await services.skills.get_skill(user_id, skill_id)
        if skill is None:
            skipped += 1
            continue

        timezone = await services.messages.profile_timezone(user_id)
        progress = await services.progress.compute(user_id, skill_id, timezone)
        behind = next((s for s in progress.steps if s.behind_cadence), None)
        if behind is None:
            skipped += 1
            continue

        step_detail = next((s for s in skill.plan.steps if s.order == behind.order), None)
        step_description = step_detail.description if step_detail else f"step {behind.order}"
        days_since = max((now - behind.anchor_at).days, 0)

        language = await services.messages.profile_language(user_id)
        status = await services.notifications.send_cadence_nudge(
            user_id, skill_id, timezone, now, language, step_description, days_since
        )
        if status == "sent":
            notified += 1
        else:
            skipped += 1

    return NotificationScanResponse(scanned=scanned, notified=notified, skipped=skipped)


@router.post("/v1/internal/sessions/summarize")
async def summarize_sessions(
    request: Request, _secret: RequireInternalSecret
) -> SessionSummarizeResponse:
    """~15-minute poll (research.md R2) — SessionSummaryService owns the
    eligibility fan-out (SQL RPC), the LLM call, and the Neo4j write."""
    services = request.app.state.services
    count = await services.session_summary.summarize_eligible_sessions()
    return SessionSummarizeResponse(sessions_summarized=count)
