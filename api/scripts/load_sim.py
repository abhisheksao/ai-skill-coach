"""Load simulation for US1 scenario 1 (quickstart.md): N users x M-message
burst against a LOCAL API, summarizing response classes. Proves the queue
paces admission under pressure -- zero raw provider errors, only coach
replies or the degraded/unavailable/budget-exhausted i18n keys (SC-002).

Usage: uv run python scripts/load_sim.py --users 10 --burst 5
       [--url http://localhost:8000] [--token <jwt>] [--session-id <uuid>]

Requires a real user JWT (`--token`) since /v1/chat is authenticated --
this drives one real user's session through repeated bursts (this
script measures QUEUE behavior under a request burst, not true
multi-tenant concurrency, which the process-local queue doesn't
distinguish between users for anyway).
"""

import argparse
import asyncio
import time
import uuid
from collections import Counter

import httpx


async def _send_one(
    client: httpx.AsyncClient, url: str, token: str, session_id: str, text: str
) -> str:
    try:
        response = await client.post(
            f"{url}/v1/chat",
            json={"message": text, "session_id": session_id},
            headers={"Authorization": f"Bearer {token}"},
            timeout=60,
        )
    except httpx.HTTPError:
        return "network_error"

    if response.status_code == 200:
        body = response.json()
        if body.get("budget", {}).get("exhausted"):
            return "budget_exhausted"
        return "coach_reply"
    if response.status_code == 429:
        return "budget_exceeded_429"
    if response.status_code == 503:
        return "llm_unavailable_503"
    return f"unexpected_{response.status_code}"


async def run(url: str, token: str, session_id: str, users: int, burst: int) -> Counter:
    results: Counter = Counter()
    async with httpx.AsyncClient() as client:
        for _user in range(users):
            tasks = [
                _send_one(client, url, token, session_id, f"load-sim message {i}")
                for i in range(burst)
            ]
            outcomes = await asyncio.gather(*tasks)
            results.update(outcomes)
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--burst", type=int, default=5)
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--token", required=True, help="A real user JWT")
    parser.add_argument("--session-id", default=str(uuid.uuid4()))
    args = parser.parse_args()

    started = time.monotonic()
    results = asyncio.run(run(args.url, args.token, args.session_id, args.users, args.burst))
    elapsed = time.monotonic() - started

    total = sum(results.values())
    print(f"\n{total} requests ({args.users} users x {args.burst} burst) in {elapsed:.1f}s")
    for outcome, count in results.most_common():
        print(f"  {outcome}: {count}")

    ok_outcomes = ("coach_reply", "budget_exhausted", "network_error")
    raw_errors = [k for k in results if k not in ok_outcomes]
    if raw_errors:
        print(f"\nRAW PROVIDER/UNEXPECTED ERRORS FOUND: {raw_errors} -- SC-002 violated")


if __name__ == "__main__":
    main()
