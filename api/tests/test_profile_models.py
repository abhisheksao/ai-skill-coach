"""Direct validation coverage for ProfileRequest's custom validators
(consent gate, IANA timezone check) -- previously only exercised
indirectly via test_profile_contract.py's HTTP-level assertions."""

import pytest
from pydantic import ValidationError

from skillcoach_api.models.profile import ProfileRequest

pytestmark = [pytest.mark.foundations, pytest.mark.profile, pytest.mark.models]


def make_request(**overrides) -> dict:
    base = {"display_name": "Priya", "language": "hi", "timezone": "Asia/Kolkata", "consent": True}
    base.update(overrides)
    return base


def test_accepts_valid_payload() -> None:
    ProfileRequest(**make_request())


def test_accepts_no_display_name() -> None:
    ProfileRequest(**make_request(display_name=None))


def test_rejects_consent_false() -> None:
    with pytest.raises(ValidationError, match="consent is required"):
        ProfileRequest(**make_request(consent=False))


def test_rejects_unsupported_language() -> None:
    with pytest.raises(ValidationError):
        ProfileRequest(**make_request(language="zz"))


def test_rejects_non_iana_timezone() -> None:
    with pytest.raises(ValidationError, match="not an IANA timezone"):
        ProfileRequest(**make_request(timezone="Not/A/Zone"))


def test_rejects_empty_display_name() -> None:
    with pytest.raises(ValidationError):
        ProfileRequest(**make_request(display_name=""))
