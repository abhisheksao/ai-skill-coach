"""Profile persistence — service-role upsert (idempotent; FR-006)."""

from datetime import UTC, datetime

from coach_core.supabase_rest import SupabaseRest


class ProfileStore:
    def __init__(self, rest: SupabaseRest) -> None:
        self._rest = rest

    async def upsert(
        self,
        user_id: str,
        display_name: str | None,
        language: str,
        timezone: str,
        voice_replies_enabled: bool = True,
    ) -> dict:
        now = datetime.now(UTC).isoformat()
        row = {
            "user_id": user_id,
            "display_name": display_name,
            "language": language,
            "timezone": timezone,
            "consent_at": now,
            "updated_at": now,
            "voice_replies_enabled": voice_replies_enabled,
        }
        returned = await self._rest.upsert("profiles", row, on_conflict="user_id")
        return returned or row
