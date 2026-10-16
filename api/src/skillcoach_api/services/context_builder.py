"""Assembles what the LLM needs each turn (FR-008): profile language,
active-skill subgraph (if any), recent conversation, turn count, a gap
description when a step is behind cadence (FR-009, SC-001), the last N
session summaries for cross-session continuity (FR-007, SC-003), and the
goal's revision trajectory when it's been revised before (FR-011,
SC-005).

No wizard/intake state is ever stored (FR-004, research R1) — the LLM
reconstructs progress purely from `recent_messages` each call.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from skillcoach_api import constants
from skillcoach_api.models.skills import GoalDetail, SkillDetail
from skillcoach_api.services.messages import MessageStore
from skillcoach_api.services.progress import ProgressService
from skillcoach_api.services.skills import SkillsService


@dataclass
class ConversationContext:
    language: str
    skill: SkillDetail | None
    recent_messages: list[dict]  # [{sender, content}], chronological
    user_turn_count: int  # BEFORE the message currently being handled
    gap_description: str | None = None  # set when the active skill has a behind-cadence step
    recent_session_summaries: list[str] = field(default_factory=list)  # most-recent-first
    goal_history: list[GoalDetail] = field(default_factory=list)  # oldest-first; current is last


class ContextBuilder:
    def __init__(
        self, messages: MessageStore, skills: SkillsService, progress: ProgressService
    ) -> None:
        self._messages = messages
        self._skills = skills
        self._progress = progress

    async def build(
        self, user_id: str, skill_id: str | None, session_id: str
    ) -> ConversationContext:
        language = await self._messages.profile_language(user_id)
        skill = await self._skills.get_skill(user_id, skill_id) if skill_id else None
        recent = await self._messages.recent_messages(session_id)
        turn_count = await self._messages.count_user_turns(session_id)

        gap_description = None
        recent_summaries: list[str] = []
        goal_history: list[GoalDetail] = []
        if skill is not None:
            gap_description = await self._build_gap_description(user_id, skill)
            recent_summaries = await self._skills.recent_session_summaries(
                user_id, skill.id, constants.SESSION_SUMMARY_COUNT
            )
            goal_history = await self._skills.goal_revision_history(user_id, skill.id)

        return ConversationContext(
            language=language,
            skill=skill,
            recent_messages=recent,
            user_turn_count=turn_count,
            gap_description=gap_description,
            recent_session_summaries=recent_summaries,
            goal_history=goal_history,
        )

    async def _build_gap_description(self, user_id: str, skill: SkillDetail) -> str | None:
        timezone = await self._messages.profile_timezone(user_id)
        progress = await self._progress.compute(user_id, skill.id, timezone)
        behind = next((s for s in progress.steps if s.behind_cadence), None)
        if behind is None:
            return None

        step = next((s for s in skill.plan.steps if s.order == behind.order), None)
        if step is None:
            return None

        days = max((datetime.now(UTC) - behind.anchor_at).days, 0)
        return f"{step.description} — {days} day(s) since last check-in"
