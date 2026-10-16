"""Direct validation coverage for RegenerateRequest -- previously only
exercised indirectly via test_skills_contract.py's HTTP-level assertions."""

import pytest
from pydantic import ValidationError

from skillcoach_api.models.skills import RegenerateRequest

pytestmark = [pytest.mark.wizard_plan, pytest.mark.skills, pytest.mark.models]


def test_accepts_each_valid_reason() -> None:
    for reason in ("too_much", "too_easy", "not_quite_right"):
        RegenerateRequest(reason=reason)


def test_rejects_unknown_reason() -> None:
    with pytest.raises(ValidationError):
        RegenerateRequest(reason="just because")


def test_note_defaults_to_none() -> None:
    assert RegenerateRequest(reason="too_much").note is None


def test_rejects_note_over_200_chars() -> None:
    with pytest.raises(ValidationError):
        RegenerateRequest(reason="too_much", note="x" * 201)
