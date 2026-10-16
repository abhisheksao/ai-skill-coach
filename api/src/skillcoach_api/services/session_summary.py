"""Session-end continuity (004, FR-006/FR-007; research.md R2). Finds
sessions past `constants.SESSION_INACTIVITY_MINUTES` of inactivity with
no `Session` node yet, summarizes via the LLM (budgeted, FR-012), and
writes `(:Skill)-[:HAS_SESSION]->(:Session)`. A summarization failure for
one session (LLM outage, budget exceeded, malformed output) is logged
and skipped — it never blocks any other session, and the candidate
simply stays eligible for the next scan (FR-006 scenario 3).
"""

import logging
from datetime import UTC, datetime, timedelta

from coach_core.analytics import SESSION_ENDED, AnalyticsService
from coach_core.supabase_rest import SupabaseRest
from skillcoach_api import constants
from skillcoach_api.models.session_summary import SessionSummary

logger = logging.getLogger(__name__)

_SESSION_EXISTS = "MATCH (sess:Session {id: $session_id}) RETURN sess LIMIT 1"

_CREATE_SESSION = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
CREATE (sess:Session {
  id: $session_id, started_at: datetime($started_at), ended_at: datetime($ended_at),
  summary: $summary
})
CREATE (s)-[:HAS_SESSION]->(sess)
"""


class SessionSummaryService:
    def __init__(
        self, rest: SupabaseRest, driver, budget, llm, analytics: AnalyticsService
    ) -> None:
        self._rest = rest
        self._driver = driver
        self._budget = budget
        self._llm = llm
        self._analytics = analytics

    async def summarize_eligible_sessions(self) -> int:
        cutoff = (
            datetime.now(UTC) - timedelta(minutes=constants.SESSION_INACTIVITY_MINUTES)
        ).isoformat()
        candidates = await self._rest.rpc("eligible_sessions_for_summary", {"cutoff": cutoff})

        summarized = 0
        for candidate in candidates:
            try:
                if await self._summarize_one(candidate):
                    summarized += 1
            except Exception as exc:
                logger.warning(
                    "session summarization failed for session %s: %s",
                    candidate.get("session_id"),
                    type(exc).__name__,
                )
        return summarized

    async def _summarize_one(self, candidate: dict) -> bool:
        session_id = candidate["session_id"]
        if await self._already_summarized(session_id):
            return False

        messages = await self._rest.select_many(
            "messages", {"session_id": session_id}, "sender,content", order="created_at.asc"
        )
        if not messages:
            return False

        user_id = candidate["user_id"]
        await self._budget.acquire(user_id)
        transcript = "\n".join(f"{m['sender']}: {m['content']}" for m in messages)
        summary_text, usage = await self._llm.generate_session_summary(transcript)
        await self._budget.report(user_id, usage)
        summary = SessionSummary(summary=summary_text)  # enforces the bounded length

        async with self._driver.session() as session:
            await session.run(
                _CREATE_SESSION,
                user_id=user_id,
                skill_id=candidate["skill_id"],
                session_id=session_id,
                started_at=candidate["started_at"],
                ended_at=candidate["ended_at"],
                summary=summary.summary,
            )
        await self._analytics.emit(
            SESSION_ENDED,
            user_id,
            {"skill_id": candidate["skill_id"], "message_count": len(messages)},
        )
        return True

    async def _already_summarized(self, session_id: str) -> bool:
        async with self._driver.session() as session:
            result = await session.run(_SESSION_EXISTS, session_id=session_id)
            record = await result.single()
        return record is not None
