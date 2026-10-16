# Implementation Plan: Progress Loop & Notifications

**Branch**: `004-progress-and-notifications` | **Date**: 2026-07-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/004-progress-and-notifications/spec.md`

## Summary

Every conversational report of practice, difficulty, or completion becomes
a typed `CheckIn` — the sole, append-only source of progress truth
(Constitution II) — via three new intents (`log_checkin`,
`report_obstacle`, `complete_step`) that join the existing
create/revise vocabulary. A new home dashboard aggregates every skill's
derived progress (streak, cadence adherence, completed steps) and lets a
step be marked done or partial with a tap that bypasses the LLM entirely,
using the exact same validate-then-translate pipeline as a
conversationally-produced intent (Constitution I, Amendment 1.5.0). A
nightly Supabase `pg_cron` job scans for users behind their plan's
cadence and sends a push notification (Expo push service) that deep-links
into the right skill's session, where the coach already knows about the
gap; a second, more frequent cron job detects abandoned/ended
conversations by inactivity and summarizes them so future sessions open
with recent context already loaded. Every new numeric threshold this
feature introduces (cadence multiplier, notification caps/quiet hours,
stale-goal window, session-inactivity timeout, session-summary count)
lives in one new `constants.py` module, not environment variables — these
are rare-to-change product tuning values, not secrets or per-deploy
config (2026-07-17 direction).

## Technical Context

**Language/Version**: unchanged — TypeScript/Expo (`app/`), Python 3.12
(`api/`).

**Primary Dependencies**: NEW client dependency — `expo-notifications`
(official Expo package; push token acquisition, permission prompts,
foreground/tap handling), configured via `app.json`'s plugin array
alongside the existing `expo-speech-recognition` entry. NEW Supabase
extensions — `pg_cron` (scheduling) and `pg_net` (outbound HTTP from a
cron job, research.md R1) — no new backend Python dependency; push sends
and the internal-secret check use the existing `httpx`/`FastAPI` stack
(research.md R3).

**Storage**: Three new Postgres tables (`cadence_schedules`,
`push_tokens`, `notifications` — data-model.md) via one new migration.
Two new Neo4j additions (`CheckIn`, `Session`), both already named,
human-approved extension points in the constitution's graph schema block
(Amendment 1.5.0). No new Neo4j node types beyond these two.

**Testing**: pytest for all new backend logic — intent→Cypher translation
for the three new intents, `ProgressService` derivation queries (streak/
cadence-adherence math against hand-computed fixtures, SC-002), the two
internal scan endpoints (cron-secret auth, frequency-cap/quiet-hours
logic, session-boundary detection), `CadenceScheduleService` sync. jest
for the dashboard screen's client-side derivation display and offline-
cache fallback. Playwright (web) + Maestro (native) for the end-to-end
loop: tap-to-complete on the dashboard, and — as far as a simulated/
fast-forwarded cadence gap can be driven in a test harness — the nudge→
tap→gap-aware-opening flow (SC-001); genuinely time-dependent real-device
delivery (does a real push arrive, does the OS notification tray deep-
link work) is a live/manual quickstart scenario, same device-dependent
carve-out as 001–003's Maestro flows (Constitution VIII).

**Target Platform**: unchanged (iOS/Android/web from one Expo codebase).
Push notifications require the mobile apps per spec Assumptions — web
users get gap-awareness in-session only (no browser push in v1).

**Project Type**: unchanged monorepo (`app/` + `api/`).

**Performance Goals**: no new latency-sensitive path — the two cron-
triggered endpoints run off the request/response critical path entirely;
`GET /v1/dashboard` and `GET /v1/skills/{id}/progress` are ordinary read
endpoints with no stated SLA beyond "responsive," consistent with 001–003.

**Constraints**: FR-004/Constitution II — every progress value is
recomputed at read time, never cached/stored; FR-018 — every threshold
lives in `constants.py`, one definition per value, no inline literals at
call sites; SC-007 — the UI-native tap path makes zero LLM calls
(verified in the intent_apply/route tests, not just documentation);
Constitution IX — `pg_cron`/`pg_net` and Expo push are both free-tier,
flagged in research.md R1 as needing live verification in the Supabase
console before implementation, per the constitution's "verify live
external limits" workflow rule.

**Scale/Scope**: three new intent types, one new UI-native route, two new
read endpoints (progress, dashboard), two new push-token endpoints, two
new internal cron-triggered endpoints, one new Postgres migration (three
tables), two new Neo4j entities, one new client dashboard screen plus a
per-skill progress screen, one new push-notification hook. No new
top-level services beyond what's listed in Project Structure below.

## Constitution Check

*GATE: evaluated against constitution v1.7.0 — re-checked after Phase 1.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | LLM never writes Cypher | PASS | Three new intents follow the existing validate-then-translate pipeline exactly; the UI-native path (`/v1/intents/apply`) skips only the LLM call, never validation or the translator (Amendment 1.5.0) — same `IntentApplyService.apply_intents`, same one-transaction guarantee. |
| II | Progress derived, never stored | PASS | `ProgressService` (research.md R7) computes completed-steps/streak/cadence-adherence from `CheckIn` at read time on every call; no counter is written anywhere. `cadence_schedules` and `notifications` are not progress values — the former is a rhythm *setting*, the latter a delivery *log* — so storing them doesn't violate this principle. |
| III | Goal history immutable; no UI delete | PASS | Not touched beyond what 002 already established; FR-017/FR-014's stale-goal card explicitly offers no delete action. |
| IV | Single message pipeline | PASS (N/A for UI-native) | Conversational check-ins are ordinary chat turns, no modality branching added. UI-native taps create no `messages` row at all — they're not a message, so Principle IV (which governs message modality) doesn't apply to them; this is the same reasoning Amendment 1.5.0 already used to broaden Principle I. |
| V | Budgeted LLM calls | PASS | Session summarization (a new LLM call type) goes through the existing per-user daily budget (`BudgetGuard`) exactly like a chat turn, using the cheap tier (FR-012). |
| VI | Provider/tier config-only | PASS (N/A) | Not touched. |
| VII | Data placement | PASS | `CheckIn`/`Session` → Neo4j (structured coaching state); `cadence_schedules`/`push_tokens`/`notifications` → Postgres (exactly the three categories the constitution's stack list names: "push tokens, cadence" plus the new delivery log alongside them). |
| VIII | Testing | PASS, scope noted | Every FR/AC/edge case gets a test per the discipline; new pytest markers needed (`progress_notifications` feature marker; `checkins`, `progress`, `cadence`, `notifications`, `dashboard`, `sessions` domain markers) — a `/speckit-tasks` task, not a plan-time change. `docs/testing.md` gains a `### Feature 004` section at the exit gate, matching the existing format. |
| IX | Cost ceiling | PASS, flagged | `pg_cron`/`pg_net` and Expo push are $0; live-verify both extensions are enabled/available on this Supabase project's actual tier before implementation begins (research.md R1) rather than trusting documentation. |
| X | Multilingual | PASS, scope noted | Notification body copy and the coach's gap-aware opening must be produced/localized for the 5 launch languages, same as every other user-facing string — no new mechanism, just new content to localize. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/004-progress-and-notifications/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md         # Phase 1 output
├── quickstart.md         # Phase 1 output
└── contracts/
    └── api.md            # Phase 1 output
                           # tasks.md — Phase 2 (/speckit-tasks, not yet created)
```

### Source Code (repository root)

```text
api/src/skillcoach_api/
├── constants.py                    # NEW: every FR-018 tunable threshold
│                                   #   (research.md R4)
├── config.py                       # EXTEND: + Settings.internal_secret
│                                   #   (research.md R1)
├── internal_auth.py                # NEW: X-Internal-Secret dependency
│                                   #   for the two internal cron routes,
│                                   #   mirroring RequirePrincipal's shape
│                                   #   (research.md R1)
├── models/
│   ├── intents.py                  # EXTEND: + LogCheckinIntent,
│   │                               #   ReportObstacleIntent,
│   │                               #   CompleteStepIntent; Intent union
│   │                               #   grows to 7 variants
│   ├── checkins.py                 # NEW: UiIntent union (complete_step |
│   │                               #   log_checkin only) + request/
│   │                               #   response models for
│   │                               #   POST /v1/intents/apply
│   ├── progress.py                 # NEW: response models for
│   │                               #   GET /v1/skills/{id}/progress and
│   │                               #   GET /v1/dashboard
│   ├── notifications.py            # NEW: push-token request/response
│   │                               #   models
│   └── session_summary.py          # NEW: internal-only SessionSummary
│                                   #   model (research.md R5) — never
│                                   #   part of the Intent union
├── routes/
│   ├── checkins.py                 # NEW: POST /v1/intents/apply
│   ├── progress.py                 # NEW: GET /v1/skills/{id}/progress,
│   │                               #   GET /v1/dashboard
│   ├── notifications.py            # NEW: POST/DELETE /v1/push-tokens
│   ├── internal.py                 # NEW: POST /v1/internal/
│   │                               #   notifications/scan,
│   │                               #   POST /v1/internal/sessions/
│   │                               #   summarize (shared-secret auth,
│   │                               #   not RequirePrincipal)
│   └── chat.py                     # EXTEND: after apply_intents, if the
│                                   #   batch contained create_plan or
│                                   #   revise_plan, call
│                                   #   CadenceScheduleService.sync(...)
├── services/
│   ├── intent_apply.py             # EXTEND: + _LOG_CHECKIN,
│   │                               #   _REPORT_OBSTACLE,
│   │                               #   _COMPLETE_STEP Cypher constants
│   │                               #   + _build branches (research.md R5)
│   ├── progress.py                 # NEW: streak/cadence-adherence/
│   │                               #   completed-steps derivation
│   │                               #   (research.md R7)
│   ├── cadence_schedule.py         # NEW: Postgres sync + read
│   │                               #   (research.md R8)
│   ├── notifications.py            # NEW: push-token lifecycle
│   │                               #   (Postgres), Expo push send
│   │                               #   (httpx), frequency-cap/quiet-
│   │                               #   hours check, delivery logging
│   │                               #   (research.md R1, R3)
│   ├── session_summary.py          # NEW: inactivity detection query
│   │                               #   (Postgres messages), cheap-tier
│   │                               #   LLM summarize call, Neo4j
│   │                               #   Session node write (research.md
│   │                               #   R2)
│   ├── context_builder.py          # EXTEND: build() also fetches last
│   │                               #   N Session summaries
│   │                               #   (constants.SESSION_SUMMARY_COUNT)
│   │                               #   and, when the skill has a
│   │                               #   behind-cadence step, a gap
│   │                               #   description — both folded into
│   │                               #   ConversationContext (FR-007,
│   │                               #   SC-001, SC-003)
│   └── container.py                # EXTEND: wire the 4 new services
└── tests/
    ├── test_intent_apply.py        # EXTEND: + log_checkin/
    │                               #   report_obstacle/complete_step
    │                               #   cases (happy path + step-not-
    │                               #   found/wrong-plan-generation
    │                               #   negative cases)
    ├── test_checkins_contract.py   # NEW: POST /v1/intents/apply —
    │                               #   validation failure surfaces
    │                               #   directly (FR-015), source is
    │                               #   always ui_tap regardless of
    │                               #   request body, zero LLM calls
    │                               #   (SC-007)
    ├── test_progress.py            # NEW: streak/cadence-adherence math
    │                               #   against hand-computed fixtures
    │                               #   (SC-002)
    ├── test_progress_contract.py   # NEW: GET .../progress,
    │                               #   GET /v1/dashboard — agreement
    │                               #   (SC-006), empty-state (FR-014
    │                               #   scenario 2)
    ├── test_cadence_schedule.py    # NEW: sync on create_plan/
    │                               #   revise_plan, replace-on-revise
    ├── test_notifications.py       # NEW: frequency cap, quiet hours,
    │                               #   OS-denied-permission no-op
    │                               #   (User Story 4 scenario 4),
    │                               #   multi-skill-behind consolidation
    ├── test_notifications_contract.py  # NEW: push-token register/
    │                               #   revoke, internal-secret auth
    ├── test_session_summary.py     # NEW: inactivity-boundary
    │                               #   detection, no-Session-yet
    │                               #   guard, summarization failure
    │                               #   doesn't break next session
    │                               #   (FR-006 scenario 3)
    └── test_context_builder.py     # EXTEND: last-N-summaries and gap
                                    #   description folded into context

supabase/migrations/
└── 2026071X_progress_notifications.sql   # NEW: cadence_schedules,
                                           #   push_tokens, notifications

app/src/
├── app/
│   ├── index.tsx                   # EXTEND: redirect target changes
│   │                               #   from /skills to /dashboard
│   └── (main)/
│       ├── dashboard.tsx           # NEW: home dashboard (User Story 6)
│       │                           #   — cards per skill, stale marking,
│       │                           #   tap-to-complete (User Story 7)
│       └── skill/[id]/progress.tsx # NEW: per-skill progress view
│                                   #   (User Story 2)
├── hooks/
│   └── use-push-notifications.ts   # NEW: registration on sign-in,
│                                   #   POSTs to /v1/push-tokens,
│                                   #   DELETEs on sign-out, handles
│                                   #   notification-tap → deep link
├── lib/
│   ├── api.ts                     # EXTEND: dashboard/progress/
│   │                               #   intents-apply/push-token calls
│   └── dashboard-cache.ts          # NEW: AsyncStorage read/write for
│                                   #   the offline stale-data fallback
│                                   #   (research.md R10)
└── app.json                        # EXTEND: expo-notifications plugin
                                   #   entry + permission strings
```

**Structure Decision**: Same monorepo, no new top-level directories. All
seven backend services stay flat siblings of the existing ones in
`services/` (no new subpackage) — matches the existing one-file-per-
concern convention (`budget.py`, `graph.py`, `messages.py`, ...). The new
`(main)/dashboard.tsx` screen becomes the app's actual landing screen by
changing top-level `index.tsx`'s redirect target from `/skills` to
`/dashboard` — `/skills` (002's list) stays reachable but is no longer
the first thing a signed-in user sees.

## Implementation Notes (how the pieces connect)

1. **Three new intents share one Cypher shape, differing only in
   `outcome`.** `log_checkin`/`report_obstacle`/`complete_step` each
   `MATCH` the target Step by `(skill_id, step_order)` within the active
   (non-superseded) Plan — never by a stored Step id, since Step has none
   (002's `data-model.md`) — then `CREATE` one `CheckIn` node with
   `outcome` fixed by intent type. This keeps `intent_apply.py`'s
   established "one Cypher constant + one `isinstance` branch per intent
   type" pattern intact rather than inventing a new dispatch shape.

2. **The UI-native path and the conversational path are the same
   pipeline past validation.** `POST /v1/intents/apply` (new) and
   `POST /v1/chat` (existing) both end at
   `IntentApplyService.apply_intents` — the only difference is which
   route calls it and whether an LLM call happened first. `source` is
   never a field the caller supplies; each route hardcodes which value
   it passes down, so a UI tap cannot masquerade as conversational
   provenance or vice versa (FR-016).

3. **Two independent pg_cron-triggered jobs, not one.** The nightly
   cadence scan (`notifications/scan`) and the ~15-minute session-
   summarize poll (`sessions/summarize`) are separate endpoints with
   separate schedules — they touch different data (cadence schedules +
   CheckIns vs. messages + Sessions) and have different urgency profiles
   (once a day vs. near-real-time continuity). Both share the same
   internal-secret auth helper (one new dependency function in
   `auth.py` or a small new `internal_auth.py`, mirroring
   `RequirePrincipal`'s shape but checking a header against
   `settings.internal_secret` instead of decoding a JWT).

4. **The cadence scan's fan-out is Postgres-only; the recency check is
   Neo4j-only.** `notifications/scan` starts by reading
   `cadence_schedules` (flat SQL — which users/skills/steps even have an
   active plan), then for each candidate queries Neo4j for that step's
   most recent `CheckIn`, applies `constants.CADENCE_BEHIND_MULTIPLIER`,
   and — only for steps that come back behind — checks
   `notifications` (Postgres) for the frequency cap/quiet-hours window
   before sending. A user behind on multiple skills gets at most one
   consolidated send per skill per day, never a burst (Edge Case),
   because the per-skill cap is checked independently per skill in the
   same scan pass.

5. **`ContextBuilder` is the seam that makes SC-001's "gap-aware
   opening" and SC-003's "references prior session" actually work.**
   `build()` gains two new context fields: the last
   `constants.SESSION_SUMMARY_COUNT` `Session` summaries for that skill
   (FR-007), and — if any step is currently behind cadence — a short
   structured gap description (which step, how long). Both are ordinary
   additions to the existing `ConversationContext` dataclass that the
   LLM prompt (`prompts.py`) already consumes; no special-casing for
   "this session started from a notification tap" is needed, because the
   gap description is present in context *any time* a step is behind,
   whether the user opened the app themselves or tapped a push.

6. **Dashboard and progress view are two grains of the same query, never
   two queries.** `GET /v1/dashboard` calls `ProgressService` once per
   skill in the same way `GET /v1/skills/{id}/progress` calls it for
   one — SC-006's "always agree" isn't a testing goal to verify after the
   fact, it's a structural consequence of there being exactly one
   progress-derivation code path.

7. **Constants, not config.** Every FR-018 threshold
   (`CADENCE_BEHIND_MULTIPLIER`, the two notification caps, quiet-hours
   bounds, `STALE_GOAL_DAYS`, `SESSION_INACTIVITY_MINUTES`,
   `SESSION_SUMMARY_COUNT`) is imported from `constants.py` everywhere
   it's used — `ProgressService`, the notifications scan, the session-
   summarize job, and the dashboard's staleness check all reference the
   same names rather than each hardcoding its own literal, so a future
   tuning change is a one-line diff reviewed like any other code change,
   not a redeploy with a different `.env`.
