"""Request/response models for POST /v1/intents/apply — the UI-native
tap-to-complete/log-partial path (User Story 7, research.md R6).
`UiIntent` is deliberately narrower than the full `Intent` union:
`ReportObstacleIntent` is excluded — an obstacle needs a coach response,
so reporting one stays conversation-only (research.md R6, User Story
1/7 split).
"""

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from skillcoach_api.models.intents import CompleteStepIntent, LogCheckinIntent

UiIntent = Annotated[
    CompleteStepIntent | LogCheckinIntent,
    Field(discriminator="type"),
]


class ApplyIntentRequest(BaseModel):
    skill_id: str
    intent: UiIntent


class ApplyIntentResponse(BaseModel):
    checkin_id: str
    applied_at: datetime
