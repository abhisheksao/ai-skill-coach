"""Every tunable threshold feature 004 introduces (FR-018, research.md R4).

Rare-to-change product tuning values, not secrets or per-deploy config —
deliberately NOT `Settings` fields (2026-07-17 direction). Every service/
query that needs one of these imports it from here rather than hardcoding
its own literal, so a future tuning change is a one-line diff.
"""

CADENCE_BEHIND_MULTIPLIER = 1.5
NOTIFICATION_MAX_PER_SKILL_PER_DAY = 1
NOTIFICATION_MAX_PER_WEEK = 3
QUIET_HOURS_START_HOUR = 8
QUIET_HOURS_END_HOUR = 20
STALE_GOAL_DAYS = 14
SESSION_INACTIVITY_MINUTES = 30
SESSION_SUMMARY_COUNT = 5

# 005 rate-limit queue (Constitution V; research.md R1). Pilot-scale tuning
# for a single always-warm process -- no distributed coordination needed at
# the ~100-user ceiling (spec Assumptions).
LLM_MAX_CONCURRENT = 4  # in-flight LLM calls admitted at once (asyncio semaphore)
LLM_MAX_RPM = 60  # provider-level token-bucket rate (gemini-flash-lite class quota headroom)
LLM_QUEUE_MAX_WAIT_SECONDS = 20  # admit() gives up and raises LlmUnavailable past this wait
