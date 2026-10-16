"""Nightly spend-threshold check (005, research.md R6). Run by
`.github/workflows/spend-check.yml`; exits non-zero when today's
estimated spend (the `ops_daily_spend` view) crosses
`SPEND_ALERT_THRESHOLD_USD`. GitHub's own workflow-failure email is the
alert channel -- no separate notification code (R6's whole point: one
mechanism, zero new vendors).
"""

import asyncio
import os
import sys
from datetime import UTC, datetime

import httpx

from coach_core.supabase_rest import SupabaseRest
from skillcoach_api.config import get_settings


async def check_spend(rest: SupabaseRest, threshold_usd: float) -> tuple[float, bool]:
    """Returns (today's estimated USD spend, whether it breaches the
    threshold). No row yet today (no calls made) means zero spend, not an
    error -- the view simply has nothing to aggregate."""
    today = datetime.now(UTC).date().isoformat()
    row = await rest.select_one("ops_daily_spend", {"day": today}, "estimated_usd")
    spend = float(row["estimated_usd"]) if row and row.get("estimated_usd") is not None else 0.0
    return spend, spend > threshold_usd


async def main() -> int:
    settings = get_settings()
    threshold = float(os.environ.get("SPEND_ALERT_THRESHOLD_USD", "5.0"))
    async with httpx.AsyncClient(timeout=30) as client:
        rest = SupabaseRest(client, settings.supabase_url, settings.supabase_service_role_key)
        spend, breached = await check_spend(rest, threshold)

    print(f"Today's estimated spend: ${spend:.4f} (threshold: ${threshold:.2f})")
    if breached:
        print("SPEND THRESHOLD BREACHED", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
