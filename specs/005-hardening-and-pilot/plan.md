# Implementation Plan: Hardening & Pilot

**Branch**: `005-hardening-and-pilot` | **Date**: 2026-07-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/005-hardening-and-pilot/spec.md`

## Summary

005 turns the working product of 001–004 into something ~100 strangers can
use unassisted. The v0 `BudgetGuard` stub is replaced (behind its existing
`acquire` seam) by the real Constitution-V queue — FIFO admission, a
provider-rate token bucket, per-user daily budgets with a per-user
override/kill-switch table — and budget exhaustion becomes a friendly
in-conversation coach message instead of a raw 429 (research.md R1, R2).
Privacy and durability move to pilot grade: the Gemini key swaps to a
billing-enabled paid-tier key (config-only, Constitution VI), the host
moves from Render free to Render Starter (the constitution's first
sanctioned spend), and a nightly GitHub Actions workflow exports the full
coaching graph to a private Supabase Storage bucket, with a written,
once-executed restore runbook (R3–R5). Observability arrives as
server-side `analytics_events` + operator SQL views (sessions, retention,
intent-failure rate, estimated daily spend from new token columns on
`llm_usage`), and three scheduled GitHub workflows whose failure emails
are the alert channel: export missed, health check down, spend threshold
crossed (R6–R8). The client closes the seven-cell voice failure matrix
with honest, specific states that never disable chat (R9), gains a
first-run onboarding explainer with contextual permission prompts, a
Settings "Delete account" entry opening a configurable URL, and Sign in
with Apple; distribution is local builds uploaded to TestFlight and Play
internal, per a written release runbook (R11–R13). Latency target
adopted: p90 reply start < 3 s warm, measured from existing request logs
(R10).

## Technical Context

**Language/Version**: unchanged — TypeScript/Expo (`app/`), Python 3.12
(`api/`); plus GitHub Actions workflow YAML (`.github/workflows/`) as a
new operational surface.

**Primary Dependencies**: NEW client dependency —
`expo-apple-authentication` (Sign in with Apple, research.md R11) and
`@react-native-community/netinfo` (offline detection for the voice/chat
failure matrix, R9) — both official/Expo-supported packages. NO new
backend Python dependency: the queue uses stdlib `asyncio`, exports use
the already-present `neo4j` driver, uploads use the already-present
`httpx` against Supabase Storage's REST API. NEW external mechanisms,
existing vendors only: GitHub Actions scheduled workflows (alerting +
export execution), Supabase Storage bucket `graph-exports`.

**Storage**: One new migration — `analytics_events` and `user_limits`
tables, `model_rates` reference table, token columns + extended
`increment_llm_usage` RPC on `llm_usage`, and the `ops_*` operator views
(data-model.md). One new private Supabase Storage bucket. No graph
schema change — the export serializes the fixed v1 schema as-is.

**Testing**: pytest — queue admission/budget/override/blocked semantics
(fake clock, no sleeps), budget-exhausted chat turn (200, zero LLM
calls, `resets_at`), usage-token recording, analytics emission at each
seam (fire-and-forget: an analytics failure never fails the request),
export/restore round-trip against the fake graph store, spend-check
threshold logic, log-redaction sentinel test (R14). jest — voice
failure-state reducers, offline queue/marked-failed logic, onboarding
gating, deletion-entry URL handling. Playwright — budget-exhausted
in-conversation message, offline compose→reconnect→send, onboarding
first-run flow, delete-account entry opens URL. Maestro + manual matrix —
the device-only voice cells (V2 revoked mid-session, V6 TTS, V7 audio
focus) and real TestFlight/Play install; each manual cell lands in
`docs/testing.md`'s checklist (Constitution VIII carve-out). Workflow
alert emails are validated by one deliberate failure each (R6).

**Target Platform**: unchanged (iOS/Android/web from one Expo codebase);
distribution channels new — TestFlight + Play internal track (R11).

**Project Type**: unchanged monorepo (`app/` + `api/`), plus
`.github/workflows/` and `docs/runbooks/`.

**Performance Goals**: p90 reply start < 3 s on the warm host (R10,
resolves the spec's only NEEDS CLARIFICATION); measured from the
existing `duration_ms` request log on `POST /v1/chat`, verified over a
real pilot day via a documented query.

**Constraints**: Constitution V — every LLM call passes the queue (the
`acquire` seam guarantees it); Constitution VI — tier switch touches
secrets/config only, proven by a zero-diff code check; Constitution IX —
exactly two sanctioned spends executed by the human (Render Starter
~$7/mo, Gemini paid tier), two store fees pre-flagged (Apple $99/yr,
Play $25 one-time) executed by the human at release time; FR-007 — no
transcript bodies or secrets in logs or analytics properties, enforced
by test; SC-002 — zero raw provider errors user-visible, enforced by the
queue + existing degraded-turn paths.

**Scale/Scope**: ~100-user ceiling (spec Assumptions) — the queue is
process-local because the warm host is a single process (R1); no
sharding/multi-region. Surface: 1 service rewrite (`budget.py` →
queue), 1 new backend service (`analytics.py`), 4 operator scripts, 3
GitHub workflows, 1 migration, 1 storage bucket, ~4 client screens/flows
touched (voice states, onboarding, settings, auth), 5 runbook docs, 2
store distributions.

## Constitution Check

*GATE: evaluated against constitution v1.8.0 — re-checked after Phase 1.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | LLM never writes Cypher | PASS | No new write paths. The export scripts are read-only against the graph; `restore_graph.py` and `delete_user.py` are operator-run, deterministic, parameterized scripts (not LLM-reachable, not client-reachable), documented in runbooks. |
| II | Progress derived, never stored | PASS | Untouched. `analytics_events` stores product telemetry, not progress; no counter feeds any user-facing progress value. |
| III | Goal history immutable | PASS, one deliberate exception | Untouched by features. The operator **deletion runbook** (R13) detach-deletes a user's whole subgraph — that is account deletion honoring a legal/privacy obligation, not a UI goal-delete; constitution's "ask before deleting data" is satisfied because the runbook is human-executed per explicit user request, never automated. |
| IV | Single message pipeline | PASS | Budget-exhausted turns are produced route-side identically regardless of modality; voice failure states are client-side pre-send affordances, nothing downstream branches on modality. |
| V | Budgeted LLM calls | PASS — this feature *implements* it | The v0 stub becomes the real queue; the `acquire` interface it promised is kept, so no call site can bypass it. Tiering (lite vs standard) unchanged from 001–004 wiring. |
| VI | Provider/tier config-only | PASS — this feature *proves* it | R3: key swap + model pin via env only; validation includes confirming zero code diff. |
| VII | Data placement | PASS | `analytics_events`, `user_limits`, `model_rates`, token columns → Postgres (operational data, exactly VII's non-graph category). Graph exports are *copies* of coaching state in access-controlled storage — placement rule governs the system of record, which stays Neo4j. |
| VIII | Testing | PASS, scope noted | Every FR/AC/edge case mapped to a test in tasks; device-only voice cells + store installs + alert emails go to the manual checklist in `docs/testing.md` (updated at exit gate). New pytest markers for the feature (`hardening`) and domains (`queue`, `analytics`, `ops`). |
| IX | Cost ceiling | PASS — the sanctioned exception | This feature is the constitution's named first spend. All four money items (Render Starter, Gemini paid, Apple Program, Play Console) are pre-flagged in `docs/getting-started.md` and executed by the human, never silently by a task. |
| X | Multilingual | PASS | All new user-facing strings (budget-exhausted reply, 7 voice states, onboarding cards, deletion entry, Apple sign-in) localized in all 5 launch languages; EN+HI full acceptance, ES/FR/DE smoke per the sampling policy. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/005-hardening-and-pilot/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/
    └── api.md           # Phase 1 output
                          # tasks.md — Phase 2 (/speckit-tasks)
```

### Source Code (repository root)

```text
api/src/skillcoach_api/
├── constants.py                    # EXTEND: LLM_MAX_CONCURRENT,
│                                   #   LLM_MAX_RPM,
│                                   #   LLM_QUEUE_MAX_WAIT_SECONDS
├── config.py                       # EXTEND: no new secrets needed for
│                                   #   the queue; verify tier switch
│                                   #   needs zero changes here (R3)
├── logging_setup.py                # EXTEND: ai_failure structured event
│                                   #   helper (R14)
├── models/
│   └── errors.py                   # EXTEND: BudgetExceeded gains
│                                   #   resets_at in the envelope (R2)
├── routes/
│   └── chat.py                     # EXTEND: catch BudgetExceeded →
│                                   #   200 budget-exhausted turn (R2);
│                                   #   emit session_started /
│                                   #   intent_validation_failed
│                                   #   analytics (R8)
├── services/
│   ├── budget.py                   # REWRITE (same interface): acquire()
│   │                               #   = user budget + override/blocked
│   │                               #   check + queue admission; report()
│   │                               #   = post-call token recording (R1,R7)
│   ├── llm_queue.py                # NEW: FIFO admission + provider
│   │                               #   token bucket (asyncio, R1)
│   ├── analytics.py                # NEW: fire-and-forget event writes
│   │                               #   (R8)
│   ├── notifications.py            # EXTEND: emit push_sent/push_failed
│   │                               #   analytics beside the existing
│   │                               #   delivery log (R8)
│   ├── session_summary.py          # EXTEND: emit session_ended (R8)
│   └── container.py                # EXTEND: wire queue + analytics
└── tests/                          # NEW: test_llm_queue, test_analytics,
                                    #   test_export_restore,
                                    #   test_spend_check,
                                    #   test_log_redaction;
                                    # EXTEND: test_budget,
                                    #   test_chat_contract (budget turn),
                                    #   test_notifications

api/scripts/
├── export_graph.py                 # NEW: graph → dated JSON → Supabase
│                                   #   Storage (R5)
├── restore_graph.py                # NEW: JSON export → empty instance
│                                   #   (R5)
├── spend_check.py                  # NEW: views → threshold exit code
│                                   #   (R6)
└── delete_user.py                  # NEW: operator account deletion
                                    #   (R13)

.github/workflows/
├── nightly-export.yml              # NEW: cron export + freshness
│                                   #   assert (R5)
├── healthcheck.yml                 # NEW: 30-min /health probe (R6)
├── spend-check.yml                 # NEW: daily threshold check (R6)
└── ci.yml                          # RESTORE: api lint+tests on push
                                    #   (deferred-from-001 item,
                                    #   getting-started.md)

supabase/migrations/
└── 20260718000001_hardening_pilot.sql  # NEW: analytics_events,
                                    #   user_limits, model_rates,
                                    #   llm_usage token columns +
                                    #   extended RPC, ops_* views

app/src/
├── app/
│   ├── (onboarding)/welcome.tsx    # NEW: first-run explainer cards,
│   │                               #   contextual notification-
│   │                               #   permission action (R12)
│   ├── (auth)/sign-in.tsx          # EXTEND: Sign in with Apple (R11)
│   └── (main)/settings.tsx         # EXTEND: Delete-account row →
│                                   #   configurable URL (R13)
├── hooks/
│   ├── use-voice-session.ts        # EXTEND: V2/V5/V6/V7 failure
│   │                               #   states (R9)
│   └── use-chat-session.ts         # EXTEND: V4 offline preserve/
│                                   #   retry/marked-failed (R9)
├── lib/
│   └── api.ts                      # EXTEND: budget-exhausted turn
│                                   #   rendering support, resets_at
└── i18n/locales/*.json             # EXTEND: all new strings × 5

docs/
├── runbooks/
│   ├── operations.md               # NEW: cost views, log policy,
│   │                               #   weekly limit review, kill
│   │                               #   switch (R7, R14, R15)
│   ├── restore.md                  # NEW: tested restore procedure (R5)
│   ├── release.md                  # NEW: TestFlight / Play internal
│   │                               #   build+upload procedure (R11)
│   ├── deletion.md                 # NEW: operator account deletion
│   │                               #   (R13)
│   └── pilot.md                    # NEW: cohort roster, invite flow,
│   │                               #   exit-bar tracking queries
├── getting-started.md                # EXTEND: mark 005 spend items as
│                                   #   executed when the human does
└── testing.md                      # EXTEND at exit gate (VIII)

render.yaml                         # EXTEND: plan: free → starter (R4)
```

**Structure Decision**: Same monorepo; the only new top-level surface is
`.github/workflows/` (which the repo already had before CI was deferred)
and `docs/runbooks/`. Operator scripts live in `api/scripts/` so they
reuse the package's driver/config code without becoming routable
endpoints. Backend services stay flat siblings per the existing
one-file-per-concern convention.

## Implementation Notes (how the pieces connect)

1. **The queue hides behind the interface the stub promised.**
   `BudgetGuard.acquire(user_id)` keeps its name and call sites. Order
   inside: check `user_limits.blocked` (kill switch) → resolve effective
   daily budget (override or default) → atomic usage increment (existing
   RPC, now returning tokens too) → over-budget raises `BudgetExceeded`
   *before* queueing → `LlmQueue.admit()` awaits a FIFO slot + provider
   token-bucket capacity, up to `LLM_QUEUE_MAX_WAIT_SECONDS`, then
   raises `LlmUnavailable` (which chat already degrades gracefully).
   A new `report(user_id, usage_metadata)` records actual tokens
   post-call. Provider 429s that still slip through hit tenacity's
   backoff exactly as today — the queue reduces their frequency; it
   doesn't replace the retry.

2. **Budget exhaustion is a turn, not an error.** `chat.py` catches
   `BudgetExceeded` and returns a 200 whose reply is the
   `errors.budget_exhausted_reply` i18n key plus `resets_at`, persisted
   the same way the degraded-validation turn is. Non-chat callers keep
   the 429 envelope (now with `resets_at`). No client version can ever
   see a raw provider or budget error in-conversation (SC-002).

3. **Alerting is "a workflow failed."** All three alerts (export,
   health, spend) are scheduled GitHub workflows that fail loudly;
   GitHub's failure email to the owner is the channel. Each is failed
   once on purpose during validation — an untested alert is not an
   alert (spec Assumptions).

4. **The export must restore, not just exist.** `export_graph.py` writes
   one JSON document (nodes + relationships, v1 schema) per night to
   the private `graph-exports` bucket; `restore_graph.py` replays one
   into an *empty* instance and re-derives counts for spot-checks. The
   round-trip runs in CI against the fake graph store on every push,
   and once for real against a scratch Aura instance before the first
   invite (SC-003) — the real run is the runbook's required rehearsal.

5. **Analytics rides existing seams, never new requests.** Every SC-005
   metric originates server-side, so `AnalyticsService.emit()` is
   called from chat (session_started, intent_validation_failed),
   session_summary (session_ended), and notifications
   (push_sent/push_failed). Emission is awaited but exception-swallowed
   (logged, never raised) — telemetry must never break coaching.

6. **Voice matrix cells are states, not toasts.** Each R9 cell maps to
   a named state in the voice/chat hooks with specific copy and a
   preserved-input guarantee; the text composer is never disabled in
   any cell. Web-testable cells get Playwright coverage; device-only
   cells (revoked-mid-session, TTS loss, audio focus) get Maestro where
   feasible and otherwise land as rows in `docs/testing.md`'s manual
   matrix — walked once per platform before the pilot.

7. **Humans spend money; tasks prepare everything else.** Tasks produce
   the one-line `render.yaml` change, the runbooks, and the config
   seams; the human performs the four pre-flagged payments/enrollments
   (Render Starter, Gemini paid key, Apple Program, Play Console) and
   records them in `docs/getting-started.md`. No task silently introduces
   spend (Constitution IX).

8. **Pilot cohort is a runbook, not a table.** Roster + beta-channel
   status live in `docs/runbooks/pilot.md`; per-user session counts
   against the ≥3-sessions exit bar come from an `ops_` view over
   analytics (SC-001). At ≤10 users, a documented query beats cohort
   infrastructure.
