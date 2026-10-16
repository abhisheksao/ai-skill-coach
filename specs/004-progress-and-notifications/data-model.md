# Data Model — Progress Loop & Notifications

## Neo4j: new node types and relationships

Both additions are already named, human-approved extension points in the
constitution's graph schema block (`constitution.md:128-131`, Amendment
1.5.0 for `CheckIn.source`):

```
(:Step)<-[:FOR_STEP]-(:CheckIn)
(:Skill)-[:HAS_SESSION]->(:Session)
```

### `CheckIn`

| Property | Type | Notes |
|---|---|---|
| `id` | `string` (UUID) | Server-generated; FR-016 provenance auditability. |
| `timestamp` | `datetime` | When the practice happened — may be in the past (Edge Case: "I swam twice over the weekend" backdates this, not `created_at`). |
| `created_at` | `datetime` | When the row was written; always "now," distinct from `timestamp`. |
| `outcome` | `"completed" \| "partial" \| "obstacle"` | Set by which intent produced it (research.md R5) — `complete_step` → `completed`, `log_checkin` → `partial`, `report_obstacle` → `obstacle`. |
| `sentiment` | `"positive" \| "neutral" \| "negative"` | Coarse, per spec Assumptions (no fine-grained emotion analysis in v1). |
| `obstacle` | `string \| null` | Required (non-null) when `outcome = "obstacle"`; optional free text on the other two outcomes. |
| `source` | `"conversation" \| "ui_tap"` | Schema approved 2026-07-13; identical progress-derivation treatment regardless of value (Constitution II). |

Relationship: `(:Step)<-[:FOR_STEP]-(:CheckIn)`, always targeting a Step
in the skill's *active* (non-superseded) Plan — a check-in can never be
recorded against a step from a superseded plan generation. Append-only:
no update or delete path exists anywhere in this feature (matches
`CheckIn`'s Key Entity description: "the sole source of progress truth").

Multiple `CheckIn` rows for the same step on the same day are all
recorded (Edge Case) — streak/cadence derivation (research.md R7)
de-duplicates by calendar date when computing a streak, so same-day
duplicates don't inflate it, but every row still exists for audit/detail
purposes (e.g. showing two separate practice notes from the same day).

### `Session`

| Property | Type | Notes |
|---|---|---|
| `id` | `string` (UUID) | **Reuses the client's existing `session_id`** (already a UUID on every `ChatRequest`) — no new id-generation or correlation step (research.md R2). |
| `started_at` | `datetime` | Timestamp of that session's first message. |
| `ended_at` | `datetime` | Timestamp of that session's last message before the inactivity gap that closed it. |
| `summary` | `string` | LLM-generated (cheap tier, FR-012), covering topics/check-ins/obstacles/commitments per FR-006. Bounded length (validated in the `SessionSummary` internal model, research.md R5). |

Relationship: `(:Skill)-[:HAS_SESSION]->(:Session)`. A session with
`skill_id IS NULL` in Postgres `messages` (the wizard flow, before a
skill exists yet) is never summarized into a `Session` node — there's no
`Skill` to attach it to, and User Story 3's continuity promise is
specifically about an *existing* skill's coaching sessions, not
onboarding.

### Progress derivation queries (no new stored state)

`services/progress.py` (research.md R7) computes, read-only, from
`CheckIn`/`Step`/`Plan` already in the graph — Constitution II: these
values are never written anywhere, not cached, always recomputed:

- Completed-step set: Steps in the active Plan with ≥1 `CheckIn
  {outcome: "completed"}`.
- Streak: distinct calendar dates (user's `profiles.timezone`) with ≥1
  `CheckIn` under the skill; longest consecutive run ending today or
  yesterday.
- Per-step behind-cadence flag: `now - max(CheckIn.timestamp) >
  constants.CADENCE_BEHIND_MULTIPLIER × (7 / Step.cadence_per_week) days`.

## Postgres: new tables (migration `supabase/migrations/2026071X_progress_notifications.sql`)

Three new tables, all service-role-only writes (matching the existing
`messages`/`llm_usage` RLS posture — clients never write these directly):

### `cadence_schedules`

Relational projection of each active step's expected rhythm
(research.md R8), synced whenever a `create_plan`/`revise_plan` intent
applies.

```sql
create table public.cadence_schedules (
    user_id uuid not null,
    skill_id text not null,
    step_order integer not null,
    cadence_per_week integer not null,
    updated_at timestamptz not null default now(),
    primary key (user_id, skill_id, step_order)
);
```

| Column | Notes |
|---|---|
| `skill_id` | `text`, matches the Neo4j `Skill.id` string (UUID), not a Postgres FK — cross-store by convention, same as `messages.skill_id`. |
| `step_order` | Matches `Step.order` within the currently-active Plan; a `revise_plan` replaces all rows for that `(user_id, skill_id)` (old step orders may no longer exist). |

### `push_tokens`

Managed lifecycle per FR-013 — multiple rows per user (one per device).

```sql
create table public.push_tokens (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    token text not null,
    platform text not null check (platform in ('ios', 'android', 'web')),
    created_at timestamptz not null default now(),
    revoked_at timestamptz
);
create unique index push_tokens_user_token_idx on public.push_tokens (user_id, token) where revoked_at is null;
```

A nudge goes to every row for that user with `revoked_at is null`
(FR-013's "each device its own token; a nudge goes to all active
tokens"). Revoked on sign-out (client calls a new `DELETE
/v1/push-tokens/{id}`); the platform's own token-rotation is handled by
re-registering (upsert on `(user_id, token)`), not by deleting the old
row proactively — a rotated-out token simply stops being sent to once the
platform stops returning it as valid and Expo's push receipt reports it
dead (standard Expo push token lifecycle).

### `notifications`

Delivery log, also the source of truth for the frequency cap (research.md
R1/R9's constants):

```sql
create table public.notifications (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null,
    skill_id text not null,
    sent_at timestamptz not null default now(),
    gap_description text not null,
    delivery_status text not null check (delivery_status in ('sent', 'failed', 'skipped_no_token', 'skipped_permission_denied')),
    created_at timestamptz not null default now()
);
create index notifications_user_sent_idx on public.notifications (user_id, sent_at);
```

The frequency cap (`constants.NOTIFICATION_MAX_PER_SKILL_PER_DAY`,
`NOTIFICATION_MAX_PER_WEEK`) is enforced by counting existing
`delivery_status = 'sent'` rows for that user/skill in the relevant
trailing window before sending another — no separate counter table,
consistent with "derived, not stored" in spirit even though this table
itself (unlike `CheckIn`) *is* the authoritative log of what was actually
sent (Constitution II governs progress/streaks/cadence specifically, not
delivery audit logs).

## Client-side (transient, not authoritative)

- **Dashboard cache** (research.md R10): last successful `GET
  /v1/dashboard` response, `AsyncStorage`, rendered with a stale-data
  indicator when a refetch fails offline — never treated as
  authoritative; overwritten by the next successful fetch.
- **Push token**: obtained via `expo-notifications`
  (`getExpoPushTokenAsync`), held in memory only long enough to POST it
  to `/v1/push-tokens` on registration/refresh — not persisted client-side
  beyond what `expo-notifications` itself caches internally.
