"""Push-token lifecycle (Postgres), Expo push delivery, and the
frequency-cap/quiet-hours gate (FR-010, FR-013; research.md R1/R3/R9).

Notification body/title copy is selected from a small server-side i18n
table keyed by `profiles.language` (Constitution X) — this is the one
user-facing string in this feature that never passes through the LLM (the
push bypasses `/v1/chat` entirely), so it can't rely on the usual "LLM
writes the reply in the target language" mechanism every other feature
uses.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from coach_core.analytics import PUSH_FAILED, PUSH_SENT, AnalyticsService
from coach_core.supabase_rest import SupabaseRest
from skillcoach_api import constants

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"

# language -> (title, body template with {step}/{days} placeholders).
# Falls back to English for any language not in this table.
_PUSH_COPY: dict[str, tuple[str, str]] = {
    "en": ("Time for a check-in?", "It's been {days} day(s) since {step}. Your coach is ready."),
    "hi": ("जांच करने का समय?", "{step} को {days} दिन हो गए हैं। आपका कोच तैयार है।"),
    "es": ("¿Hora de retomar?", "Han pasado {days} día(s) desde {step}. Tu coach está listo."),
    "fr": ("On reprend ?", "Cela fait {days} jour(s) depuis {step}. Votre coach est prêt."),
    "de": (
        "Zeit für ein Check-in?",
        "Es ist {days} Tag(e) her seit {step}. Dein Coach ist bereit.",
    ),
}


def _push_copy(language: str, step_description: str, days: int) -> tuple[str, str]:
    title, body_template = _PUSH_COPY.get(language, _PUSH_COPY["en"])
    return title, body_template.format(step=step_description, days=days)


class NotificationsService:
    def __init__(
        self, rest: SupabaseRest, http_client: httpx.AsyncClient, analytics: AnalyticsService
    ) -> None:
        self._rest = rest
        self._http = http_client
        self._analytics = analytics

    # -------------------------------------------------------- push tokens

    async def register_token(self, user_id: str, token: str, platform: str) -> None:
        # Select-then-branch, not an upsert: push_tokens' uniqueness is a
        # PARTIAL index (WHERE revoked_at IS NULL, migration 20260717000001)
        # so it allows a revoked row and a fresh active row to coexist for
        # the same (user_id, token) — Postgres can't infer a partial index
        # from a plain ON CONFLICT (user_id, token), which 42P10s (found via
        # live device testing, 2026-07-18: every registration was silently
        # failing this way, masked until then by the separate Firebase gap).
        existing = await self._rest.select_one(
            "push_tokens", {"user_id": user_id, "token": token}, "id"
        )
        if existing:
            await self._rest.update(
                "push_tokens",
                {"user_id": user_id, "token": token},
                {"platform": platform, "revoked_at": None},
            )
        else:
            await self._rest.insert(
                "push_tokens",
                [{"user_id": user_id, "token": token, "platform": platform, "revoked_at": None}],
            )

    async def revoke_token(self, user_id: str, token: str) -> None:
        await self._rest.update(
            "push_tokens",
            {"user_id": user_id, "token": token},
            {"revoked_at": datetime.now(UTC).isoformat()},
        )

    async def active_tokens(self, user_id: str) -> list[str]:
        rows = await self._rest.select_many(
            "push_tokens",
            {"user_id": user_id},
            "token",
            raw_filters={"revoked_at": "is.null"},
        )
        return [row["token"] for row in rows]

    # ---------------------------------------------------------- gating

    def is_daytime(self, now: datetime, timezone: str) -> bool:
        local_hour = now.astimezone(ZoneInfo(timezone)).hour
        return constants.QUIET_HOURS_START_HOUR <= local_hour < constants.QUIET_HOURS_END_HOUR

    async def within_frequency_cap(self, user_id: str, skill_id: str, now: datetime) -> bool:
        day_ago = (now - timedelta(days=1)).isoformat()
        week_ago = (now - timedelta(days=7)).isoformat()

        per_skill_today = await self._rest.select_many(
            "notifications",
            {"user_id": user_id, "skill_id": skill_id, "delivery_status": "sent"},
            "id",
            raw_filters={"sent_at": f"gte.{day_ago}"},
        )
        if len(per_skill_today) >= constants.NOTIFICATION_MAX_PER_SKILL_PER_DAY:
            return False

        per_user_this_week = await self._rest.select_many(
            "notifications",
            {"user_id": user_id, "delivery_status": "sent"},
            "id",
            raw_filters={"sent_at": f"gte.{week_ago}"},
        )
        return len(per_user_this_week) < constants.NOTIFICATION_MAX_PER_WEEK

    # ------------------------------------------------------------- send

    async def send_cadence_nudge(
        self,
        user_id: str,
        skill_id: str,
        timezone: str,
        now: datetime,
        language: str,
        step_description: str,
        days_since: int,
    ) -> str | None:
        """Returns the delivery_status that was logged, or None when
        skipped by a scheduling gate (quiet hours / frequency cap) --
        those are pre-send decisions, not delivery outcomes, so nothing is
        logged for them (the `notifications` table's check constraint has
        no status value for "not even attempted")."""
        if not self.is_daytime(now, timezone):
            return None
        if not await self.within_frequency_cap(user_id, skill_id, now):
            return None

        audit_description = f"{step_description} — {days_since}d since last check-in"
        tokens = await self.active_tokens(user_id)
        if not tokens:
            await self._log(user_id, skill_id, audit_description, "skipped_no_token")
            return "skipped_no_token"

        title, body = _push_copy(language, step_description, days_since)
        status = await self._send_expo_push(tokens, title, body, skill_id)
        await self._log(user_id, skill_id, audit_description, status)
        if status == "sent":
            await self._analytics.emit(PUSH_SENT, user_id, {"skill_id": skill_id})
        elif status == "failed":
            await self._analytics.emit(
                PUSH_FAILED, user_id, {"skill_id": skill_id, "reason": "provider_error"}
            )
        return status

    async def _send_expo_push(self, tokens: list[str], title: str, body: str, skill_id: str) -> str:
        messages = [
            {
                "to": token,
                "title": title,
                "body": body,
                "data": {"skill_id": skill_id, "url": f"skillcoach://skill/{skill_id}/session"},
            }
            for token in tokens
        ]
        try:
            response = await self._http.post(_EXPO_PUSH_URL, json=messages)
            response.raise_for_status()
        except httpx.HTTPError:
            return "failed"

        # Check for any success FIRST: a user can have multiple tokens (one
        # per device), and one dead/malformed entry must never mask a
        # genuine delivery to another (found live, 2026-07-18 -- a stray
        # malformed token registered alongside a valid one made an actual
        # successful send report as skipped_permission_denied instead).
        results = response.json().get("data", [])
        if any(r.get("status") == "ok" for r in results):
            return "sent"
        if any(
            r.get("status") == "error"
            and r.get("details", {}).get("error") == "DeviceNotRegistered"
            for r in results
        ):
            return "skipped_permission_denied"
        return "failed"

    async def _log(self, user_id: str, skill_id: str, gap_description: str, status: str) -> None:
        await self._rest.insert(
            "notifications",
            [
                {
                    "user_id": user_id,
                    "skill_id": skill_id,
                    "gap_description": gap_description,
                    "delivery_status": status,
                }
            ],
        )
