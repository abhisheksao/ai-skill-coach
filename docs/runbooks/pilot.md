# Pilot Runbook

Cohort roster, invite flow, and exit-bar tracking for the ~100-user
pilot (005, US5). Deliberately a runbook + SQL view, not a database
table (plan.md note 8) — at this scale a table adds migration surface
with no query it would improve.

## Invite flow

1. Confirm `docs/getting-started.md`'s spend rows are all executed
   (Render Starter, paid Gemini key, Apple Developer Program, Play
   Console) and `docs/runbooks/release.md`'s build/upload has landed on
   both stores' internal tracks.
2. Add the invitee to the roster table below with today's date and
   `invited` status.
3. Send the TestFlight (iOS) or Play internal-track (Android) invite
   link/email per `docs/runbooks/release.md`.
4. Once they complete their first session, update their roster row's
   status to `active`.

## Roster

| Date invited | Platform | Status (invited / active / churned) | Notes |
|---------------|----------|-----------------------------------------|-------|
| _(pending — pilot not yet started)_ | | | |

## Exit-bar tracking (SC-001)

The pilot's exit bar is **≥ 3 completed sessions per pilot user**,
answered directly from analytics — no separate cohort infrastructure
needed:

```sql
select * from ops_pilot_exit_bar order by completed_sessions desc;
```

`meets_exit_bar` is `true` once a user's `session_ended` count reaches
3. Cross-reference against the roster above by matching `user_id` to
the invitee (via Supabase Authentication → Users, search by email).

## Issue-triage log

Real issues found during the pilot (bugs, confusing UX, missed nudges,
etc.) — not a substitute for the repo's own issue tracker if one is in
use, just a lightweight running log tied to pilot dates for the exit
review (SC-001–SC-005).

| Date | Reporter | Issue | Resolution |
|------|----------|-------|------------|
| _(pending — pilot not yet started)_ | | | |
