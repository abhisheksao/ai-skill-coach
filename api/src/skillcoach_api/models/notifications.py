"""Request models for POST/DELETE /v1/push-tokens (004, FR-013)."""

from typing import Literal

from pydantic import BaseModel, Field


class RegisterPushTokenRequest(BaseModel):
    token: str = Field(min_length=1)
    platform: Literal["ios", "android", "web"]


class RevokePushTokenRequest(BaseModel):
    token: str = Field(min_length=1)
