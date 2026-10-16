"""Response models for GET /v1/skills, GET /v1/skills/{id}, and
POST /v1/skills/{id}/plan/regenerate."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SkillSummary(BaseModel):
    """List-card shape (GET /v1/skills)."""

    id: str
    name: str
    created_at: datetime
    goal_statement: str
    target_date: date
    step_count: int


class GoalDetail(BaseModel):
    statement: str
    target_date: date


class StepDetail(BaseModel):
    order: int
    description: str
    cadence_per_week: int


class PlanDetail(BaseModel):
    id: str
    generation: int
    steps: list[StepDetail]


class SkillDetail(BaseModel):
    id: str
    name: str
    goal: GoalDetail
    plan: PlanDetail


class SkillsListResponse(BaseModel):
    skills: list[SkillSummary]


class RegenerateRequest(BaseModel):
    reason: Literal["too_much", "too_easy", "not_quite_right"]
    note: str | None = Field(default=None, max_length=200)


class RegenerateResponse(BaseModel):
    reply: str
    plan: PlanDetail
