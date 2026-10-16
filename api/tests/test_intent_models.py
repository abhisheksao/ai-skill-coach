"""Direct Pydantic validation coverage for the intent vocabulary
(Constitution I) -- previously only exercised indirectly through HTTP-level
contract tests. Every Field boundary here is what actually stands between
malformed LLM output and a graph write."""

import pytest
from pydantic import TypeAdapter, ValidationError

from skillcoach_api.models.intents import (
    CreatePlanIntent,
    CreateSkillIntent,
    Intent,
    ReviseGoalIntent,
    RevisePlanIntent,
    StepPayload,
)

pytestmark = [pytest.mark.wizard_plan, pytest.mark.intents, pytest.mark.models]

VALID_STEP = {"description": "Float and glide", "order": 1, "cadence_per_week": 3}


def make_plan_kwargs(**overrides) -> dict:
    base = {
        "type": "create_plan",
        "skill_name": "Swimming",
        "goal_statement": "Swim 1km",
        "target_date": "2026-12-01",
        "weekly_days": 3,
        "weekly_minutes_per_day": 30,
        "steps": [VALID_STEP, VALID_STEP, VALID_STEP],
    }
    base.update(overrides)
    return base


def test_step_payload_accepts_valid_bounds() -> None:
    StepPayload(**VALID_STEP)


@pytest.mark.parametrize(
    "overrides",
    [
        {"description": ""},
        {"description": "x" * 201},
        {"order": 0},
        {"order": 13},
        {"cadence_per_week": 0},
        {"cadence_per_week": 15},
    ],
)
def test_step_payload_rejects_out_of_bounds_fields(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        StepPayload(**{**VALID_STEP, **overrides})


def test_create_skill_intent_accepts_valid_name() -> None:
    CreateSkillIntent(type="create_skill", name="Swimming")


@pytest.mark.parametrize("name", ["", "x" * 81])
def test_create_skill_intent_rejects_name_out_of_bounds(name: str) -> None:
    with pytest.raises(ValidationError):
        CreateSkillIntent(type="create_skill", name=name)


def test_create_plan_intent_accepts_valid_payload() -> None:
    CreatePlanIntent(**make_plan_kwargs())


@pytest.mark.parametrize(
    "overrides",
    [
        {"steps": [VALID_STEP, VALID_STEP]},  # below min_length=3
        {"steps": [VALID_STEP] * 13},  # above max_length=12
        {"weekly_days": 0},
        {"weekly_days": 8},
        {"weekly_minutes_per_day": 4},
        {"weekly_minutes_per_day": 241},
        {"goal_statement": ""},
        {"goal_statement": "x" * 301},
    ],
)
def test_create_plan_intent_rejects_out_of_bounds_fields(overrides: dict) -> None:
    with pytest.raises(ValidationError):
        CreatePlanIntent(**make_plan_kwargs(**overrides))


def test_revise_plan_intent_requires_three_to_twelve_steps() -> None:
    RevisePlanIntent(type="revise_plan", steps=[VALID_STEP, VALID_STEP, VALID_STEP])
    with pytest.raises(ValidationError):
        RevisePlanIntent(type="revise_plan", steps=[VALID_STEP])


def test_revise_goal_intent_accepts_valid_payload() -> None:
    ReviseGoalIntent(type="revise_goal", goal_statement="Swim 2km", target_date="2027-01-01")


def test_revise_goal_intent_rejects_empty_statement() -> None:
    with pytest.raises(ValidationError):
        ReviseGoalIntent(type="revise_goal", goal_statement="", target_date="2027-01-01")


_intent_adapter: TypeAdapter = TypeAdapter(Intent)


def test_intent_union_dispatches_by_type_discriminator() -> None:
    parsed = _intent_adapter.validate_python({"type": "create_skill", "name": "Chess"})
    assert isinstance(parsed, CreateSkillIntent)


def test_intent_union_rejects_unknown_type() -> None:
    with pytest.raises(ValidationError):
        _intent_adapter.validate_python({"type": "delete_everything", "name": "Chess"})
