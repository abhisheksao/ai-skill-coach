"""Typed intent vocabulary for 002 (Constitution I; constitution v1.5.0
schema). Validated against these schemas before any Cypher runs; the
translator (services/intent_apply.py) is the only path from here to a
write.

`RevisePlanIntent`/`ReviseGoalIntent` deliberately carry no skill
identifier: they always apply to whichever skill the conversation is
already scoped to (the caller passes that id straight to
`apply_intents`), never a name the LLM would have to echo back correctly
— see intent_apply.py's module docstring for why a name would be
ambiguous once FR-012 allows duplicate names. `CreatePlanIntent` keeps
`skill_name` since it's naturally present at wizard completion (the LLM
just named the skill) and is a cheap consistency signal, though the
translator matches by the id generated for the paired `create_skill`
regardless.
"""

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field


class StepPayload(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    order: int = Field(ge=1, le=12)
    cadence_per_week: int = Field(ge=1, le=14)


class CreateSkillIntent(BaseModel):
    type: Literal["create_skill"]
    name: str = Field(min_length=1, max_length=80)


class CreatePlanIntent(BaseModel):
    type: Literal["create_plan"]
    skill_name: str = Field(min_length=1, max_length=80)
    goal_statement: str = Field(min_length=1, max_length=300)
    target_date: date
    weekly_days: int = Field(ge=1, le=7)
    weekly_minutes_per_day: int = Field(ge=5, le=240)
    steps: list[StepPayload] = Field(min_length=3, max_length=12)


class RevisePlanIntent(BaseModel):
    type: Literal["revise_plan"]
    steps: list[StepPayload] = Field(min_length=3, max_length=12)


class ReviseGoalIntent(BaseModel):
    type: Literal["revise_goal"]
    goal_statement: str = Field(min_length=1, max_length=300)
    target_date: date


Sentiment = Literal["positive", "neutral", "negative"]


class LogCheckinIntent(BaseModel):
    """Partial progress on a step (004, FR-001/FR-002). `step_order` is
    matched against the skill's active Plan by IntentApplyService, never a
    stored Step id (Step has none, 002 data-model.md). `timestamp` is
    optional -- omitted means "just now"; set it when the user reports past
    practice (Edge Case: "I swam twice over the weekend")."""

    type: Literal["log_checkin"]
    step_order: int = Field(ge=1, le=12)
    outcome: Literal["partial"]
    sentiment: Sentiment
    obstacle: str | None = Field(default=None, max_length=300)
    timestamp: datetime | None = None


class ReportObstacleIntent(BaseModel):
    type: Literal["report_obstacle"]
    step_order: int = Field(ge=1, le=12)
    obstacle: str = Field(min_length=1, max_length=300)
    sentiment: Sentiment
    timestamp: datetime | None = None


class CompleteStepIntent(BaseModel):
    type: Literal["complete_step"]
    step_order: int = Field(ge=1, le=12)
    sentiment: Sentiment
    timestamp: datetime | None = None


Intent = Annotated[
    CreateSkillIntent
    | CreatePlanIntent
    | RevisePlanIntent
    | ReviseGoalIntent
    | LogCheckinIntent
    | ReportObstacleIntent
    | CompleteStepIntent,
    Field(discriminator="type"),
]
