"""Error envelope shared by all endpoints (contracts/api.md).

Every error body is {"error": {"code": ..., "message_key": ...}}; message_key is
an i18n catalog key the client renders in the profile language (Constitution X).
"""

from datetime import datetime


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message_key: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message_key = message_key
        super().__init__(code)


def error_body(code: str, message_key: str, resets_at: datetime | None = None) -> dict:
    body = {"error": {"code": code, "message_key": message_key}}
    if resets_at is not None:
        body["error"]["resets_at"] = resets_at.isoformat().replace("+00:00", "Z")
    return body


class Unauthorized(ApiError):
    def __init__(self) -> None:
        super().__init__(401, "unauthorized", "errors.unauthorized")


class BudgetExceeded(ApiError):
    """005, contracts/api.md: `resets_at` is the UTC start of the next
    budget day (the `usage_date` boundary `llm_usage` already uses) --
    omitted for the kill-switch (`user_limits.blocked`) case, which has no
    automatic reset."""

    def __init__(self, resets_at: datetime | None = None) -> None:
        super().__init__(429, "budget_exceeded", "errors.budget_exceeded")
        self.resets_at = resets_at


class LlmUnavailable(ApiError):
    def __init__(self) -> None:
        super().__init__(503, "llm_unavailable", "errors.llm_unavailable")
