# Phase 0 Research — Progress Loop & Notifications

## R1: Daily cadence scan mechanism

**Decision**: Supabase `pg_cron` schedules a nightly job that calls
`net.http_post` (the `pg_net` extension) against a new internal FastAPI
endpoint, `POST /v1/internal/notifications/scan`, authenticated by a
shared-secret header (`X-Internal-Secret`, compared to a new
`Settings.internal_secret`) rather than a user JWT — there is no
authenticated user for a cron trigger. The endpoint itself does the real
work (compute behind-cadence users, apply the frequency cap/quiet hours,
send pushes) in Python, not SQL.

**Rationale**: The constitution's stack list already names `pg_cron` as
the mechanism (`constitution.md:141`, "Supabase (..., cadence, pg_cron)").
But the behind-cadence computation needs the *last check-in per step*,
which lives in Neo4j (Constitution VII), not Postgres — so pg_cron can't
compute the answer in pure SQL. Its job is only to be the trigger;
`pg_net` (a Supabase-bundled extension for outbound HTTP from Postgres)
is the standard way a `pg_cron` job reaches an external HTTP service. This
keeps all business logic in one place (the Python backend, same as every
other write path) and treats pg_cron as scheduling infrastructure only —
consistent with Constitution I/II (derived reads, single write path) and
avoids duplicating cadence logic in two languages.

**Alternatives considered**: A Render Cron Job service (Render supports a
dedicated Cron Job resource type) was considered and rejected — it would
mean two independent schedule configurations to keep in sync across
providers, whereas pg_cron is already the constitution-named tool and
lives next to the cadence data it schedules around. An in-process Python
scheduler (APScheduler) inside the FastAPI app was also rejected: Render's
free tier can cold-start/sleep the single web process, making an
in-process timer unreliable — an external trigger (pg_cron) firing an
HTTP request is robust to that.

**Verification needed before implementation**: confirm `pg_cron` and
`pg_net` are both enabled/available on this project's Supabase tier (free
tier does support both as of general availability, but per the
constitution's Development Workflow rule, live limits must be checked in
the actual project console, not assumed from documentation).

## R2: Session-end detection (FR-006)

**Decision**: There is no explicit "end session" signal from the client
today — `session_id` (`ChatRequest.session_id`) is a UUID the client
already manages, but nothing marks it closed. 004 adds a second internal,
pg_cron/pg_net-triggered endpoint, `POST /v1/internal/sessions/summarize`,
polling every 15 minutes. It finds every distinct `(skill_id, session_id)`
pair in `messages` where `skill_id` is not null, the most recent
message's `created_at` is older than the configured inactivity timeout
(30 min default, `constants.SESSION_INACTIVITY_MINUTES`), and no `Session`
node with that id exists in Neo4j yet. For each, it summarizes the
session's messages with the cheap LLM tier (FR-012, budgeted per FR-005/
Constitution V) and writes the summary as a new `(:Session)` node.

**Rationale**: An inactivity-based, poll-driven boundary handles both
"abandoned conversations" and normal goodbyes uniformly (FR-006 requires
abandoned sessions to be summarized too, not just explicit endings) — a
session simply becomes eligible once nothing new arrives for the timeout
window, regardless of why. Reusing the client's own `session_id` as the
Neo4j `Session.id` needs no new id-generation or correlation step.

**Alternatives considered**: An explicit `POST /v1/chat/end-session` call
from the client was rejected — it adds a new client responsibility (call
it on backgrounding/navigation-away) that's easy to miss, exactly the
"abandoned conversation" case FR-006 calls out as a requirement, not an
edge case to shrug off.

## R3: Push notification delivery

**Decision**: Expo's push notification service (`https://exp.host/--/api/v2/push/send`),
called directly via the existing `httpx` client (no new SDK dependency) —
consistent with how `SupabaseRest` already wraps raw REST calls rather
than pulling in a heavier client library. Push tokens are Expo push
tokens, obtained client-side via `expo-notifications` and registered to a
new `push_tokens` Postgres table (FR-013).

**Rationale**: Expo's push service is free and is the constitution-named
mechanism (`expo-notifications` in the Architectural Constraints stack
list) — it already fans out to APNs/FCM so the backend never talks to
Apple/Google directly. A raw `httpx.post` to Expo's HTTP API needs no new
package, matching Constitution IX's cost ceiling and this codebase's
existing preference for thin wrappers over the actual current pattern
(`SupabaseRest`) instead of SDKs.

**Alternatives considered**: `exponent-server-sdk-python` (a community
Python wrapper) was considered and rejected — it's an unnecessary
dependency for what is, per Expo's own docs, a single JSON POST with a
predictable response shape; the existing codebase convention is to wrap
REST calls directly (see `SupabaseRest`) rather than adopt an SDK per
external service.

## R4: Tunable thresholds as code constants, not env vars

**Decision**: A new module, `api/src/skillcoach_api/constants.py`, holds
every threshold this feature introduces as a plain named Python constant
— not environment variables / `Settings` fields (per explicit product
direction, 2026-07-17). Initial values: `CADENCE_BEHIND_MULTIPLIER = 1.5`,
`NOTIFICATION_MAX_PER_SKILL_PER_DAY = 1`, `NOTIFICATION_MAX_PER_WEEK = 3`,
`QUIET_HOURS_START_HOUR = 8`, `QUIET_HOURS_END_HOUR = 20`,
`STALE_GOAL_DAYS = 14`, `SESSION_INACTIVITY_MINUTES = 30`,
`SESSION_SUMMARY_COUNT = 5`.

**Rationale**: These are rare-to-change tuning parameters, not secrets
and not values that vary by deploy environment — a code constant is a
single source of truth that every service/query imports, versioned and
reviewed like any other code change, with no env-var/deploy-config
indirection to keep in sync across Render environments. This is a
deliberate contrast with `config.py`'s `Settings` (secrets, per-deploy
infra values, Constitution VI provider/tier switches) — `constants.py` is
for values that change by product decision, reviewed in a PR, not by
redeploying with a different `.env`.

**Alternatives considered**: Adding these as `Settings` fields (the
`config.py`/`.env` pattern already used for `daily_llm_budget` etc.) was
the first design and was explicitly rejected by product direction in favor
of code constants, precisely because these values are rare-to-change and
not secrets — env vars are reserved for things that vary by deploy or must
never enter the repo.

## R5: New intent types (`log_checkin`, `report_obstacle`, `complete_step`)

**Decision**: Three new Pydantic models join the `Intent` discriminated
union in `models/intents.py`, following the existing `Revise*Intent`
pattern of carrying no skill identifier (the caller already knows which
skill/step is in scope) but adding a `step_order: int` field, since `Step`
has no `id` property (`data-model.md`, 002) — only `order` within the
active (non-superseded) Plan:

- `LogCheckinIntent`: `step_order`, `outcome: Literal["partial"]`
  (fixed), `sentiment: Literal["positive","neutral","negative"]`,
  `obstacle: str | None`.
- `ReportObstacleIntent`: `step_order`, `obstacle: str` (required, unlike
  the optional field on the other two), `sentiment` same enum.
- `CompleteStepIntent`: `step_order`, `sentiment` same enum, no obstacle
  field (a completion isn't a struggle report).

All three create a `CheckIn` node (`data-model.md`) differing only in
`outcome` (`"completed" | "partial" | "obstacle"`) and whether `obstacle`
is populated — one Cypher shape, three `outcome` values, matching FR-001's
framing of check-ins as one record shape with an optional obstacle field.

**Rationale**: Reusing one underlying write shape for all three intents
(rather than three unrelated Cypher statements) keeps `intent_apply.py`'s
existing "each intent type is one Cypher constant + one `isinstance`
branch" pattern intact, and matches the spec's Key Entity definition of
`CheckIn` as a single record type with an outcome/obstacle/sentiment
shape regardless of which conversational path produced it.

**`summarize_session` is deliberately NOT part of the `Intent` union.**
It's never produced by an LLM parsing user conversation and never
client-constructed (unlike the UI-native `complete_step`/`log_checkin`
path) — it's generated entirely server-side by the R2 inactivity job. A
separate internal `SessionSummary` Pydantic model (session id, summary
text, bounded length) is used only inside `session_summary.py`; keeping it
out of the `Intent` union means `/v1/chat` and `/v1/intents/apply` both
reject it outright if an LLM ever hallucinated it in `ChatTurn.intents` —
defense in depth, not just documentation.

## R6: UI-native intent bypass endpoint

**Decision**: `POST /v1/intents/apply`, a new route accepting a narrower
union — `UiIntent = CompleteStepIntent | LogCheckinIntent` (no
`ReportObstacleIntent`; reporting an obstacle needs a coach response, so
it stays conversation-only per User Story 1/7's split) — plus a required
`skill_id` field (there's no ambient chat context to infer it from, unlike
`/v1/chat`). The route forces `source="ui_tap"` server-side (FR-016 — the
client never supplies `source`; it's derived from which endpoint was
called, not client input) and calls the same
`IntentApplyService.apply_intents`, so validation and the Cypher
translator are byte-for-byte the one path both intent origins share
(Constitution I, Amendment 1.5.0).

**Rationale**: This is the amendment's whole point — a UI-native intent
"validates against the same schema and is applied by the same translator
as any LLM-produced intent," with the LLM call itself skipped, not the
validation/apply pipeline. On a validation failure, FR-015 requires
surfacing the error directly (no LLM retry path exists for this case) —
the route returns the same `{error: {code, message_key}}` envelope as
every other endpoint, just with no retry loop wrapping it.

**Alternatives considered**: Routing UI-native taps through `/v1/chat`
with a synthetic message string (e.g. `"[tap] complete step 3"`) was
rejected — it would still invoke the LLM (violating SC-007's "zero LLM
calls" requirement) and conflates a structured action with the
free-text/LLM-parsing pipeline the amendment explicitly says to skip.

## R7: Progress derivation (streak, cadence adherence, completed steps)

**Decision**: A new read-only `services/progress.py`, Cypher queries
scoped by `user_id` (Constitution I) over `CheckIn` nodes only — no
counters written anywhere (Constitution II). Three derived values per
skill:

- **Completed steps**: a Step in the active (non-superseded) Plan counts
  as complete if it has ≥1 `CheckIn {outcome: "completed"}` — matches
  002's `data-model.md` note that Step has no status property.
- **Streak**: distinct calendar dates (in the user's IANA timezone,
  already on `profiles.timezone` since 001) with ≥1 `CheckIn` anywhere
  under that skill, then the length of the current consecutive run
  ending today or yesterday (clarified 2026-07-17: per-skill calendar-day
  streak, not per-step cadence adherence).
- **Cadence adherence / behind-cadence**: for each step, expected
  interval = `7 / cadence_per_week` days; a step is "behind" when the
  gap since its most recent `CheckIn` exceeds
  `constants.CADENCE_BEHIND_MULTIPLIER × expected_interval` — the exact
  same constant and formula the R1 notification scan uses, so the
  progress view and the nudge trigger can never disagree about what
  "behind" means.

**Rationale**: Sharing one constant and one formula between the
progress view's cadence-adherence display and the notification scan's
trigger condition (rather than two independently-tuned thresholds) is a
direct consequence of FR-008's clarified definition — both consumers read
`constants.CADENCE_BEHIND_MULTIPLIER`, so tuning it in one place changes
both consistently.

## R8: Cadence schedule sync to Postgres

**Decision**: A new `cadence_schedules` Postgres table (one row per
skill/step, `cadence_per_week`, `updated_at`), populated by a new
`CadenceScheduleService.sync(...)` call made from `routes/chat.py` right
after `IntentApplyService.apply_intents` succeeds for a batch containing
`create_plan` or `revise_plan` — the two intent types that (re)define a
plan's steps.

**Rationale**: FR-008's `Cadence schedule` Key Entity is explicitly a
*relational* record ("Constitution VII — lives in the relational store"),
separate from `Step.cadence_per_week` in Neo4j — this flat Postgres
projection lets the R1 notifications scan start from a plain SQL query
("every user with an active cadence schedule row") instead of first
walking the entire Neo4j graph just to enumerate which skills/steps exist
across all users, before it ever needs to check per-step CheckIn recency.
It also means the cron job's fan-out step (which users/skills to even
consider) has no Neo4j dependency, only the per-candidate recency check
does.

**Alternatives considered**: Skipping the Postgres projection and having
the scan query Neo4j directly for every user's every skill/step was
rejected — it would mean the nightly scan does a full-graph read with no
Postgres-side filtering at all, more expensive and further from "cadence
... lives in the relational store" as the spec's Key Entities section
already states.

## R9: Home dashboard aggregation

**Decision**: `GET /v1/dashboard`, composing the already-existing
`SkillsService.list_skills` (skill/goal/plan summary) with the new
`ProgressService` (per-skill completed/streak/cadence) and a staleness
check (`STALE_GOAL_DAYS` against the most recent `CheckIn` timestamp
across the skill, or the skill's `created_at` if it has none yet). No new
Neo4j node or Postgres table — the spec's Key Entities section is explicit
that the dashboard "is not a stored entity."

**Rationale**: Matches SC-006 directly — the dashboard and each skill's
dedicated progress view must always agree because they're the same
underlying query composed at two different granularities (all skills vs.
one), never a separately cached value.

## R10: Offline dashboard state

**Decision**: The client caches the last successful `/v1/dashboard`
response in `AsyncStorage` and renders it with a "last updated" /
stale-data indicator when a refetch fails while offline — the same
pattern the spec's edge cases section points to as established in
feature 001 ("FR-007-equivalent for reads").

**Rationale**: Explicitly called for in 004's own Edge Cases section;
reusing 001's precedent means no new offline-caching pattern is invented
for this one screen.
