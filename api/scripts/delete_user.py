"""Operator account-deletion script (005, US5, research.md R13). Reached
only via `docs/runbooks/deletion.md` -- Settings' "Delete account" row
just opens a request URL; actual deletion is operator-executed.

Deletes a single user's entire footprint: the Neo4j subgraph (walking
every Goal/Plan SUPERSEDES chain, not just the active generation -- none
of this is shared with other users, per Constitution I's per-user
scoping) and every Postgres row keyed by that user_id, plus the Supabase
auth user itself (via GoTrue's admin API, not PostgREST). Confirmation
required unless `--yes`; `--dry-run` reports subgraph counts without
deleting anything. A non-existent user is a safe no-op throughout --
DETACH DELETE and filtered deletes on zero matches simply do nothing.
"""

import argparse
import asyncio
import sys

import httpx
from neo4j import AsyncGraphDatabase

from coach_core.supabase_rest import SupabaseRest
from skillcoach_api.config import get_settings

_COUNT_SUBGRAPH = """
MATCH (u:User {id: $user_id})
OPTIONAL MATCH (u)-[:PURSUES]->(s:Skill)
OPTIONAL MATCH (s)-[:HAS_GOAL]->(:Goal)-[:SUPERSEDES*0..]->(g:Goal)
OPTIONAL MATCH (s)-[:HAS_PLAN]->(:Plan)-[:SUPERSEDES*0..]->(p:Plan)
OPTIONAL MATCH (p)-[:HAS_STEP]->(st:Step)
OPTIONAL MATCH (s)-[:HAS_SESSION]->(sess:Session)
OPTIONAL MATCH (st)<-[:FOR_STEP]-(c:CheckIn)
RETURN count(DISTINCT s) AS skills, count(DISTINCT g) AS goals, count(DISTINCT p) AS plans,
       count(DISTINCT st) AS steps, count(DISTINCT sess) AS sessions, count(DISTINCT c) AS checkins
"""

_DELETE_SUBGRAPH = """
MATCH (u:User {id: $user_id})
OPTIONAL MATCH (u)-[:PURSUES]->(s:Skill)
OPTIONAL MATCH (s)-[:HAS_GOAL]->(:Goal)-[:SUPERSEDES*0..]->(g:Goal)
OPTIONAL MATCH (s)-[:HAS_PLAN]->(:Plan)-[:SUPERSEDES*0..]->(p:Plan)
OPTIONAL MATCH (p)-[:HAS_STEP]->(st:Step)
OPTIONAL MATCH (s)-[:HAS_SESSION]->(sess:Session)
OPTIONAL MATCH (st)<-[:FOR_STEP]-(c:CheckIn)
DETACH DELETE u, s, g, p, st, sess, c
"""

# Order doesn't matter -- none of these reference each other via FKs this
# script needs to respect; each delete is scoped to its own user column
# independently. `analytics_events` uses `user_sub` (not `user_id`) and
# has no FK/cascade to auth.users (migration 20260718000001) -- without
# an explicit delete here, a user's pseudonymous events would silently
# outlive the rest of their footprint, contradicting research.md R13's
# "messages, usage, tokens, notifications, analytics" deletion list.
_POSTGRES_TABLES = (
    ("messages", "user_id"),
    ("llm_usage", "user_id"),
    ("push_tokens", "user_id"),
    ("notifications", "user_id"),
    ("cadence_schedules", "user_id"),
    ("user_limits", "user_id"),
    ("analytics_events", "user_sub"),
    ("profiles", "user_id"),
)


async def count_subgraph(driver, user_id: str) -> dict:
    async with driver.session() as session:
        result = await session.run(_COUNT_SUBGRAPH, user_id=user_id)
        record = await result.single()
    return dict(record) if record else {}


async def delete_subgraph(driver, user_id: str) -> None:
    async with driver.session() as session:
        await session.run(_DELETE_SUBGRAPH, user_id=user_id)


async def delete_postgres_rows(rest: SupabaseRest, user_id: str) -> None:
    for table, filter_key in _POSTGRES_TABLES:
        await rest.delete(table, {filter_key: user_id})


async def delete_auth_user(
    http_client: httpx.AsyncClient, supabase_url: str, service_role_key: str, user_id: str
) -> None:
    response = await http_client.delete(
        f"{supabase_url.rstrip('/')}/auth/v1/admin/users/{user_id}",
        headers={"Authorization": f"Bearer {service_role_key}", "apikey": service_role_key},
    )
    if response.status_code not in (200, 204, 404):  # 404 = already gone, safe no-op
        response.raise_for_status()


async def delete_user(
    driver,
    rest: SupabaseRest,
    http_client: httpx.AsyncClient,
    supabase_url: str,
    service_role_key: str,
    user_id: str,
) -> dict:
    """Full per-user deletion. Returns the pre-deletion subgraph counts
    for the operator's own record (R13's deletion runbook log)."""
    counts = await count_subgraph(driver, user_id)
    await delete_subgraph(driver, user_id)
    await delete_postgres_rows(rest, user_id)
    await delete_auth_user(http_client, supabase_url, service_role_key, user_id)
    return counts


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, help="Supabase auth user id (uuid)")
    parser.add_argument("--yes", action="store_true", help="Skip the confirmation prompt")
    parser.add_argument(
        "--dry-run", action="store_true", help="Report subgraph counts without deleting anything"
    )
    return parser.parse_args()


async def main(args: argparse.Namespace) -> int:
    settings = get_settings()
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )
    try:
        counts = await count_subgraph(driver, args.user_id)
        print(f"User {args.user_id} subgraph: {counts}")

        if args.dry_run:
            print("Dry run -- nothing deleted.")
            return 0

        if not args.yes:
            prompt = f"Permanently delete user {args.user_id} and all their data? [y/N] "
            confirm = await asyncio.to_thread(input, prompt)
            if confirm.strip().lower() != "y":
                print("Aborted.")
                return 1

        async with httpx.AsyncClient(timeout=30) as http_client:
            rest = SupabaseRest(
                http_client, settings.supabase_url, settings.supabase_service_role_key
            )
            await delete_user(
                driver,
                rest,
                http_client,
                settings.supabase_url,
                settings.supabase_service_role_key,
                args.user_id,
            )
    finally:
        await driver.close()

    print(f"Deleted user {args.user_id}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(_parse_args())))
