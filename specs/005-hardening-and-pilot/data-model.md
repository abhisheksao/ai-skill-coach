# Data Model: Hardening & Pilot (005)

**Date**: 2026-07-18 | **Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

No Neo4j schema change in this feature — the graph's fixed v1 schema is
what gets exported/restored, byte-for-byte. Everything below is Supabase
Postgres (Constitution VII: operational data) or Supabase Storage, in one
migration: `supabase/migrations/20260718000001_hardening_pilot.sql`.
All tables are service-role-only (RLS enabled, no policies), matching the
`llm_usage`/`notifications` posture.

## Changed: `llm_usage` (Usage record — spec Key Entity)

Existing: `user_id`, `usage_date`, `count`. 005 adds token accounting so
spend is estimable per user-day (research.md R7).

| Column | Type | Notes |
|--------|------|-------|
| `prompt_tokens` | bigint not null default 0 | accumulated actuals from LangChain `usage_metadata` |
| `output_tokens` | bigint not null default 0 | ditto |

**RPC changes**: `increment_llm_usage(uid)` keeps its call-counting
contract (the pre-call budget gate). A new
`record_llm_tokens(uid, p_prompt bigint, p_output bigint)` accumulates
actuals post-call — separate function because tokens are only known
after the call returns, while the count must be reserved before it.
Both remain service-role-only (`revoke execute ... from public, anon,
authenticated`).

## New: `user_limits` (per-user override / kill switch)

Consulted by `BudgetGuard.acquire` (R1); rows exist only for exceptions —
absence means defaults apply.

| Column | Type | Notes |
|--------|------|-------|
| `user_id` | uuid PK, references auth.users | |
| `daily_budget_override` | int null | null = use `DAILY_LLM_BUDGET`; 0 = effectively paused |
| `blocked` | boolean not null default false | hard kill switch — acquire raises immediately |
| `note` | text null | operator's reason (e.g. "runaway client loop 2026-08-02") |
| `updated_at` | timestamptz not null default now() | |

**Validation**: `daily_budget_override >= 0` check constraint.

## New: `model_rates` (reference data for spend estimation)

Seeded by the migration; a price change is an `UPDATE`, not a deploy (R7).

| Column | Type | Notes |
|--------|------|-------|
| `model` | text PK | e.g. `gemini-3.1-flash-lite` |
| `usd_per_1m_prompt_tokens` | numeric not null | |
| `usd_per_1m_output_tokens` | numeric not null | |
| `updated_at` | timestamptz not null default now() | |

## New: `analytics_events` (Analytics event — spec Key Entity)

Server-side writes only (R8). Pseudonymous; `properties` MUST never
contain message/transcript bodies or secrets (FR-007; enforced by the
redaction test and review).

| Column | Type | Notes |
|--------|------|-------|
| `id` | bigint identity PK | |
| `occurred_at` | timestamptz not null default now() | |
| `user_sub` | uuid null | pseudonymous subject; null for system events |
| `event_type` | text not null | check-constrained to the vocabulary below |
| `properties` | jsonb not null default '{}' | small structured context |

**Event vocabulary (v1)** — additions allowed later; each emission point
is named in plan.md note 5:

| `event_type` | Emitted from | `properties` |
|---|---|---|
| `session_started` | chat route, first message after a session boundary | `skill_id` |
| `session_ended` | session_summary service, on summarize | `skill_id`, `message_count` |
| `intent_validation_failed` | chat route, on validation-retry exhaustion (degraded turn) | `endpoint`, `attempts` |
| `push_sent` | notifications service | `skill_id` |
| `push_failed` | notifications service | `skill_id`, `reason` (provider class, no payload) |

**Index**: `(occurred_at)`, `(event_type, occurred_at)` — the views below
scan by day and type.

## New: operator views (`ops_*`) — the cost/analytics "dashboards"

Read in the Supabase SQL editor (US4: no SSH); documented with example
output in `docs/runbooks/operations.md`.

| View | Grain | Answers |
|------|-------|---------|
| `ops_daily_spend` | day | `llm_usage` tokens × `model_rates` → estimated USD + total calls (US1 sc.3; SC-004). Rate applied is the current pinned model's — single-model deploys per Constitution VI keep this honest. |
| `ops_user_daily_usage` | user × day | per-user calls + tokens; feeds the cost-spike edge case and FR-003 |
| `ops_daily_sessions` | day | `session_started`/`session_ended` counts (SC-005) |
| `ops_retention` | day | distinct active `user_sub` today ∩ any prior activity window (SC-005 retention) |
| `ops_intent_failure_rate` | day | `intent_validation_failed` / `session_started`-proxied turns (SC-005) |
| `ops_push_outcomes` | day | sent vs failed from `analytics_events` (FR-008; cross-checkable against 004's `notifications` delivery log) |
| `ops_pilot_exit_bar` | user | completed-session count per pilot user vs the ≥3 bar (SC-001), consumed by `docs/runbooks/pilot.md` |

## New: Supabase Storage bucket `graph-exports` (Export artifact — spec Key Entity)

Private bucket, service-role access only (spec edge case: backups are
access-controlled).

**Object naming**: `graph-export-YYYY-MM-DD.json` (UTC date).

**Document shape** (written by `export_graph.py`, consumed by
`restore_graph.py`):

```json
{
  "exported_at": "2026-07-19T02:00:00Z",
  "schema_version": "v1",
  "counts": {"nodes": {"User": 12, "Skill": 30, "...": 0}, "relationships": {"PURSUES": 30, "...": 0}},
  "nodes": [{"labels": ["User"], "key": "...", "properties": {}}],
  "relationships": [{"type": "PURSUES", "start_key": "...", "end_key": "...", "properties": {}}]
}
```

`counts` is written from a second, independent aggregation query so the
restore's spot-check (SC-003) verifies against a number the row dump
didn't produce. Retention: keep-forever is fine at pilot scale (~KBs/night
vs 1 GB free); deletion obligations extend to future exports after an
account deletion (R13) — past artifacts age out per the runbook.

## Entity not modeled: Pilot cohort

Deliberately a runbook + view, not a table (plan.md note 8): roster and
beta-channel status live in `docs/runbooks/pilot.md`; the exit bar is the
`ops_pilot_exit_bar` view filtered to the roster's subs. At ≤10 users a
table adds migration surface with no query it would improve.

## State transitions

- `user_limits.blocked`: false → true (operator kill switch) → false;
  every flip is a manual operator action recorded via `note`.
- Export artifact: absent → written (nightly) → verified (restore
  rehearsal touches one artifact at least once before pilot start).
- No other entity has lifecycle transitions; `analytics_events` and
  `llm_usage` are append/accumulate-only.
