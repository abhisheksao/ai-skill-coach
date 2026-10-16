"""Response models for GET /v1/skills/{id}/progress (User Story 2) and
GET /v1/dashboard (User Story 6, Phase 7 — the exact same shape at
coarser grain, contracts/api.md). Mapped from ProgressService's
SkillProgress/StepProgress dataclasses rather than reusing them directly,
so internal-only fields (e.g. StepProgress.anchor_at) never leak into the
public API shape.
"""

from datetime import date, datetime

from pydantic import BaseModel

from skillcoach_api.services.progress import SkillProgress


class StepProgressResponse(BaseModel):
    order: int
    completed: bool
    behind_cadence: bool
    last_checkin_at: datetime | None


class SkillProgressResponse(BaseModel):
    skill_id: str
    completed_steps: list[int]
    total_steps: int
    streak_days: int
    steps: list[StepProgressResponse]

    @classmethod
    def from_domain(cls, progress: SkillProgress) -> "SkillProgressResponse":
        return cls(
            skill_id=progress.skill_id,
            completed_steps=progress.completed_steps,
            total_steps=progress.total_steps,
            streak_days=progress.streak_days,
            steps=[
                StepProgressResponse(
                    order=step.order,
                    completed=step.completed,
                    behind_cadence=step.behind_cadence,
                    last_checkin_at=step.last_checkin_at,
                )
                for step in progress.steps
            ],
        )


class DashboardSkillProgress(BaseModel):
    """Same numbers as SkillProgressResponse, summarized to a count
    instead of a step list — SC-006's "always agree" is a structural
    consequence of both reading the same ProgressService.compute() call,
    not a separately maintained guarantee."""

    completed_steps: int
    total_steps: int
    streak_days: int


class DashboardStepCard(BaseModel):
    """Per-step detail (User Story 7, Phase 8) -- the dashboard needs this
    to render a tap-to-complete/log-partial affordance per step, not just
    an aggregate count. `description` comes from the Plan (SkillsService.
    get_skill); `completed`/`behind_cadence` from the same ProgressService
    call the card's aggregate numbers already use."""

    order: int
    description: str
    completed: bool
    behind_cadence: bool


class DashboardSkillCard(BaseModel):
    skill_id: str
    name: str
    goal_statement: str
    target_date: date
    is_stale: bool
    progress: DashboardSkillProgress
    steps: list[DashboardStepCard]


class DashboardResponse(BaseModel):
    skills: list[DashboardSkillCard]
