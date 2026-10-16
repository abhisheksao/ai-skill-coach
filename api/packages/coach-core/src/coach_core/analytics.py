"""Server-side product telemetry (005, research.md R8).

Written only from backend seams that already see the event -- no client SDK,
no new endpoint. `emit()` is fire-and-forget: an analytics failure is logged
and swallowed, never raised, so telemetry can never break coaching (plan.md
note 5). `properties` MUST never contain message/transcript bodies or
secrets (FR-007) -- callers pass only small structured context.
"""

import logging

from coach_core.supabase_rest import SupabaseRest

logger = logging.getLogger(__name__)

# Event vocabulary (v1) -- must match the migration's analytics_events
# event_type check constraint (data-model.md).
SESSION_STARTED = "session_started"
SESSION_ENDED = "session_ended"
INTENT_VALIDATION_FAILED = "intent_validation_failed"
PUSH_SENT = "push_sent"
PUSH_FAILED = "push_failed"


class AnalyticsService:
    def __init__(self, rest: SupabaseRest) -> None:
        self._rest = rest

    async def emit(
        self, event_type: str, user_sub: str | None, properties: dict | None = None
    ) -> None:
        try:
            await self._rest.insert(
                "analytics_events",
                [{"event_type": event_type, "user_sub": user_sub, "properties": properties or {}}],
            )
        except Exception as exc:
            logger.warning(
                "analytics emit failed (event_type=%s): %s", event_type, type(exc).__name__
            )
