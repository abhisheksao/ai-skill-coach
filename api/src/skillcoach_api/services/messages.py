"""Message persistence — the API is the single writer (Constitution IV;
research R9). user_id comes from the verified JWT, never from the client;
modality is the caller's already-validated ChatRequest.modality (003) —
this is the only place it's used; nothing upstream of this call (context
builder, LLM prompt, intent apply) ever sees it."""

from coach_core.supabase_rest import SupabaseRest


class MessageStore:
    def __init__(self, rest: SupabaseRest) -> None:
        self._rest = rest

    async def insert_turn(
        self,
        user_id: str,
        session_id: str,
        skill_id: str | None,
        user_text: str,
        assistant_text: str,
        modality: str = "chat",
    ) -> None:
        common = {
            "user_id": user_id,
            "session_id": session_id,
            "skill_id": skill_id,
            "modality": modality,
        }
        await self._rest.insert(
            "messages",
            [
                {**common, "sender": "user", "content": user_text},
                {**common, "sender": "assistant", "content": assistant_text},
            ],
        )

    async def profile_language(self, user_id: str) -> str:
        row = await self._rest.select_one("profiles", {"user_id": user_id}, "language")
        return row["language"] if row else "en"

    async def profile_timezone(self, user_id: str) -> str:
        """Used by ProgressService (004) for streak calendar-day boundaries
        (research.md R7) -- same profiles-table read pattern as
        profile_language above."""
        row = await self._rest.select_one("profiles", {"user_id": user_id}, "timezone")
        return row["timezone"] if row else "UTC"

    async def recent_messages(self, session_id: str, limit: int = 20) -> list[dict]:
        """Chronological (oldest first); used as wizard/coaching context
        since intake facts are never persisted separately (research R1)."""
        rows = await self._rest.select_many(
            "messages",
            {"session_id": session_id},
            "sender,content",
            order="created_at.desc",
            limit=limit,
        )
        return list(reversed(rows))

    async def count_user_turns(self, session_id: str) -> int:
        """Drives the 12-turn force-summarize cap (FR-010) — no separate
        counter, just count existing rows."""
        rows = await self._rest.select_many(
            "messages", {"session_id": session_id, "sender": "user"}, "id"
        )
        return len(rows)
