"""Profile-step models (FR-010/011/012)."""

from typing import Literal
from zoneinfo import available_timezones

from pydantic import BaseModel, Field, field_validator

_VALID_TIMEZONES = available_timezones()


class ProfileRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    language: Literal["en", "hi", "es", "fr", "de"]
    timezone: str
    consent: bool
    voice_replies_enabled: bool = True

    @field_validator("consent")
    @classmethod
    def consent_must_be_given(cls, value: bool) -> bool:
        if value is not True:
            raise ValueError("consent is required")
        return value

    @field_validator("timezone")
    @classmethod
    def timezone_must_be_iana(cls, value: str) -> str:
        if value not in _VALID_TIMEZONES:
            raise ValueError("not an IANA timezone")
        return value


class ProfileResponse(BaseModel):
    profile: dict
