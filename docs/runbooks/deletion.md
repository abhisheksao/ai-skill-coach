# Account Deletion Runbook

Operator-executed account deletion (005, US5, research.md R13). Settings'
"Delete account" row only opens a request URL in the system browser — it
does not delete anything itself; this runbook is how the operator
actually fulfills that request.

## Procedure

1. Confirm the requester's identity via the email they used to sign up
   (the request URL / support channel should capture this).
2. Find their Supabase auth user id: Supabase Dashboard → Authentication
   → Users → search by email → copy the UUID.
3. **Dry run first** — report what would be deleted without touching
   anything:

   ```bash
   cd api
   uv run python scripts/delete_user.py --user-id <uuid> --dry-run
   ```

   Reports the subgraph counts (skills, goals, plans, steps, sessions,
   check-ins) that would be removed.
4. Execute for real (interactive confirmation prompt, or `--yes` to skip
   it in a scripted context):

   ```bash
   uv run python scripts/delete_user.py --user-id <uuid>
   ```

   Deletes, in order: the full Neo4j subgraph (every Goal/Plan
   `SUPERSEDES` generation, not just the active one — none of a user's
   data is shared with other users, so this is safe), every Postgres row
   keyed by that `user_id` (`messages`, `llm_usage`, `push_tokens`,
   `notifications`, `cadence_schedules`, `user_limits`, `profiles`) plus
   `analytics_events` (keyed by `user_sub`, its pseudonymous-subject
   column — no `user_id` column there, and no FK/cascade to the auth
   user, so this table needs its own explicit delete), and finally the
   Supabase auth user itself via the admin API.
5. **Verify** in the Supabase dashboard: the user no longer appears
   under Authentication → Users; a `select` for their `user_id` across
   the tables above (and `user_sub` for `analytics_events`) returns zero
   rows.
6. **Verify** in Neo4j Browser / `cypher-shell`:
   `MATCH (u:User {id: '<uuid>'}) RETURN u` returns nothing.
7. Record the deletion below.

## Export-retention note (spec edge case)

Past nightly `graph-exports` artifacts are **not** retroactively edited
— an artifact from before a deletion still contains that user's data,
by design (rewriting historical backups on every deletion request isn't
practical at pilot scale and isn't what the exports are for). Deletion
obligations apply going forward: once removed, the user's data will not
appear in any *future* export. This is disclosed in the policy page the
"Delete account" row links to.

## Deletion log

| Date | Requester (email, redacted after) | Subgraph counts (dry run) | Verified |
|------|-------------------------------------|------------------------------|----------|
| _(pending — first real deletion request during the pilot)_ | | | |
