"""Chat pipeline models. ChatTurn is the fixed LLM envelope {reply, intents[]}
(decision 2026-07-12, option A). `intents` is a discriminated union of the
v1 intent vocabulary (research R7) — 001 used a permissive list[dict]
placeholder since it always applied none; 002 is the first feature to
actually apply them.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from skillcoach_api.models.intents import Intent


class ChatTurn(BaseModel):
    """Structured output the LLM must return on every turn."""

    reply: str = Field(description="The coach's conversational reply, in the user's language")
    intents: list[Intent] = Field(
        default_factory=list,
        description="Typed intents to apply; empty when the turn changes no state",
    )
    suggested_replies: list[str] = Field(
        default_factory=list,
        max_length=6,
        description=(
            "Optional short tappable quick-reply options, in the user's language, for "
            "closed-set questions (e.g. experience level, practice frequency). Empty for "
            "open-ended questions where free text is more natural. Additive only -- the "
            "user can always type instead."
        ),
    )


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: UUID
    skill_id: UUID | None = None
    new_skill_name: str | None = Field(default=None, min_length=1, max_length=80)
    modality: Literal["chat", "voice"] = "chat"


class BudgetStatus(BaseModel):
    """005, contracts/api.md R2: additive turn field -- absent on every
    normal turn. `resets_at` is omitted (None) for the kill-switch case
    (`user_limits.blocked`), which has no automatic reset."""

    exhausted: bool
    resets_at: datetime | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: UUID
    skill_id: UUID | None
    intents: list[Intent]
    suggested_replies: list[str]
    budget: BudgetStatus | None = None
