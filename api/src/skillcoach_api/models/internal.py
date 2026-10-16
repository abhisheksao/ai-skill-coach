"""Response models for the internal, shared-secret-authenticated
cron-triggered endpoints (004, contracts/api.md) — summary counts for
logging/observability, never consumed by any client."""

from pydantic import BaseModel


class NotificationScanResponse(BaseModel):
    scanned: int
    notified: int
    skipped: int


class SessionSummarizeResponse(BaseModel):
    sessions_summarized: int
