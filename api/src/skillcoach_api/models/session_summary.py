"""Internal-only session summary (004, FR-006/FR-007; research.md R5) —
LLM-generated (cheap tier, budgeted per FR-012). Deliberately NOT part of
the `Intent` union: never producible by an LLM parsing user conversation
and never client-constructed, so a hallucinated `summarize_session` in a
`ChatTurn.intents` would be rejected outright by both `/v1/chat` and
`/v1/intents/apply` if it ever appeared there — defense in depth, not
just documentation.
"""

from pydantic import BaseModel, Field


class SessionSummary(BaseModel):
    summary: str = Field(min_length=1, max_length=800)
