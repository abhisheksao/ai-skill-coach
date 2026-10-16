"""plan_similarity: order-insensitive, normalized-text similarity guard."""

import pytest

from skillcoach_api.models.intents import StepPayload
from skillcoach_api.services.plan_similarity import is_materially_similar

pytestmark = [pytest.mark.wizard_plan, pytest.mark.plan]


def _steps(*descriptions: str) -> list[StepPayload]:
    return [
        StepPayload(order=i + 1, description=d, cadence_per_week=3)
        for i, d in enumerate(descriptions)
    ]


def test_identical_plans_are_similar() -> None:
    plan = _steps("Float and glide drills", "Kick drills", "Full stroke practice")
    assert is_materially_similar(plan, plan) is True


def test_reordered_but_same_steps_are_similar() -> None:
    old = _steps("Float and glide drills", "Kick drills", "Full stroke practice")
    new = _steps("Kick drills", "Full stroke practice", "Float and glide drills")
    assert is_materially_similar(old, new) is True


def test_trivial_rewording_is_similar() -> None:
    old = _steps("Float and glide drills", "Kick drills", "Full stroke practice")
    new = _steps("Float and glide drill", "Kick drill", "Full stroke practise")
    assert is_materially_similar(old, new) is True


def test_meaningfully_different_plan_is_not_similar() -> None:
    old = _steps("Float and glide drills", "Kick drills", "Full stroke practice")
    new = _steps(
        "Breathing exercises at the wall",
        "Treading water for 2 minutes",
        "Backstroke introduction",
    )
    assert is_materially_similar(old, new) is False


def test_different_step_count_is_never_similar() -> None:
    old = _steps("Float and glide drills", "Kick drills")
    new = _steps("Float and glide drills", "Kick drills", "Full stroke practice")
    assert is_materially_similar(old, new) is False
