# Tasks: Hardening & Pilot

**Input**: Design documents from `/specs/005-hardening-and-pilot/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: MANDATORY per Constitution VIII — every user story phase below includes unit, contract, and UX-workflow test tasks. Device-only and paid-channel scenarios land in `docs/testing.md`'s manual checklist (T063).

**Organization**: Grouped by user story. Phase order follows spec priority (P1 → P2) with one deliberate exception: US5 (P1) runs last because it is the capstone — the spec itself says "everything above serves it," and its independent test (a stranger installs and completes sessions unaided) can only pass once US1–US4 are live.

**Human-only tasks**: Constitution IX — tasks marked **[HUMAN]** involve spend or paid enrollment and are performed by the owner, never by the implementing agent. Agent tasks prepare everything up to that line.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: US1–US5 from spec.md

---

## Phase 1: Setup

**Purpose**: Dependencies, markers, and constants every story builds on

- [x] T001 Register new pytest markers `hardening`, `queue`, `analytics`, `ops` in `api/pyproject.toml` (alongside existing feature/domain markers)
- [x] T002 [P] Install client dependencies: `npx expo install @react-native-community/netinfo expo-apple-authentication` in `app/` (updates `app/package.json`; plugin entries in `app/app.json` if the packages require them)
- [x] T003 [P] Add queue constants `LLM_MAX_CONCURRENT`, `LLM_MAX_RPM`, `LLM_QUEUE_MAX_WAIT_SECONDS` to `api/src/skillcoach_api/constants.py` (research.md R1; values documented inline as pilot-scale tuning)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The migration (tables/views every story reads) and the shared analytics service

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Write migration `supabase/migrations/20260718000001_hardening_pilot.sql` per data-model.md: `analytics_events` (+ event_type check + indexes), `user_limits` (+ check constraint), `model_rates` (+ seed rows for the pinned model), `llm_usage` token columns, `record_llm_tokens` RPC (service-role-only, matching `increment_llm_usage`'s revoke posture), all seven `ops_*` views, and the private `graph-exports` storage bucket
- [x] T005 [P] Implement `AnalyticsService` in `api/src/skillcoach_api/services/analytics.py`: `emit(event_type, user_sub, properties)` — inserts via `SupabaseRest`, awaited but exception-swallowed with a warning log (fire-and-forget, plan.md note 5); event vocabulary as constants matching the migration's check
- [x] T006 [P] Unit tests for `AnalyticsService` in `api/tests/test_analytics.py`: successful emit, insert-failure swallowed (request never raises), properties never contain a message-body key (negative case)
- [x] T007 Wire `AnalyticsService` into `api/src/skillcoach_api/services/container.py` and extend `api/tests/test_container.py`

**Checkpoint**: Migration applies cleanly; analytics service available to all stories

---

## Phase 3: User Story 1 — Heavy use never breaks the product or the budget (Priority: P1) 🎯 MVP

**Goal**: Real Constitution-V queue behind the existing `acquire` seam; budget exhaustion becomes a friendly in-conversation turn; operator cost views + spend alert + kill switch

**Independent Test**: quickstart.md US1 — scripted load past provider limits and past one user's budget: zero raw provider errors, friendly budget message with reset expectation, accurate usage in `ops_*` views

### Tests for User Story 1 (write first, ensure they FAIL)

- [x] T008 [P] [US1] Unit tests for the queue in `api/tests/test_llm_queue.py`: FIFO admission order, concurrency cap respected, token-bucket pacing (fake clock, no real sleeps), `LLM_QUEUE_MAX_WAIT_SECONDS` exceeded → `LlmUnavailable`
- [x] T009 [P] [US1] Extend `api/tests/test_budget.py`: over-budget raises before queueing, `daily_budget_override` honored (including 0 = paused), `blocked=true` raises immediately, `report()` records tokens via the new RPC, absence of a `user_limits` row means defaults
- [x] T010 [P] [US1] Extend `api/tests/test_chat_contract.py`: budget-exhausted chat returns **200** with `reply="errors.budget_exhausted_reply"`, `budget.exhausted=true`, correct UTC-midnight `resets_at`, zero LLM invocations (fake runnable never called), turn persisted like the degraded turn; blocked user gets same shape without `resets_at` (contracts/api.md)
- [x] T011 [P] [US1] Unit tests for spend check in `api/tests/test_spend_check.py`: under-threshold exits 0, over-threshold exits non-zero, missing view data handled
- [x] T012 [P] [US1] Playwright: budget-exhausted message renders as a normal coach bubble in-conversation with localized copy and reset time, chat input still enabled, in `app/e2e/playwright/budget-005.spec.ts` (mock API 200 budget turn)

### Implementation for User Story 1

- [x] T013 [P] [US1] Implement `LlmQueue` in `api/src/skillcoach_api/services/llm_queue.py`: asyncio FIFO admission (semaphore `LLM_MAX_CONCURRENT`) + provider token bucket (`LLM_MAX_RPM`), `admit()` waits up to `LLM_QUEUE_MAX_WAIT_SECONDS` then raises `LlmUnavailable`; injectable clock/sleep for tests (research.md R1)
- [x] T014 [P] [US1] Extend `BudgetExceeded` in `api/src/skillcoach_api/models/errors.py` with optional `resets_at`, rendered into the error envelope (contracts/api.md)
- [x] T015 [US1] Rewrite `BudgetGuard` in `api/src/skillcoach_api/services/budget.py` (same `acquire(user_id)` interface, plan.md note 1): `user_limits` blocked check → effective budget (override or default) → existing `increment_llm_usage` RPC → over-budget raises `BudgetExceeded(resets_at)` → `LlmQueue.admit()`; add `report(user_id, usage_metadata)` calling `record_llm_tokens` (zero-fallback when metadata absent); wire queue via `container.py` (depends on T013, T014)
- [x] T016 [US1] Call `budget.report(...)` with actual token usage after each LLM call at the chat/session-summary call sites in `api/src/skillcoach_api/routes/chat.py` and `api/src/skillcoach_api/services/session_summary.py`
- [x] T017 [US1] Catch `BudgetExceeded` in `api/src/skillcoach_api/routes/chat.py` → 200 budget-exhausted turn (`errors.budget_exhausted_reply` + `budget` object), persisted like the degraded-validation turn; non-chat surfaces keep the 429 envelope (research.md R2)
- [x] T018 [US1] Render the budget turn in the client: `app/src/lib/api.ts` (parse `budget` object) and the chat screen path (`app/src/hooks/use-chat-session.ts`) — coach-style bubble, localized reset time, composer stays enabled
- [x] T019 [P] [US1] Add `errors.budget_exhausted_reply` (and any reset-time formatting strings) to all five locale files `app/src/i18n/locales/{en,hi,es,fr,de}.json` (Constitution X)
- [x] T020 [P] [US1] Implement `api/scripts/spend_check.py`: read `ops_daily_spend` via Supabase REST, compare against `SPEND_ALERT_THRESHOLD_USD` env, non-zero exit over threshold (research.md R6)
- [x] T021 [P] [US1] Implement `api/scripts/load_sim.py`: N users × M-message burst against a local API, summary of response classes (quickstart US1 step 1 driver)
- [x] T022 [P] [US1] Create workflow `.github/workflows/spend-check.yml`: daily cron + `workflow_dispatch`, runs `spend_check.py` with repo secrets, fails on threshold breach → GitHub failure email is the alert
- [x] T023 [P] [US1] Create `docs/runbooks/operations.md` (first sections): cost views usage with example queries/output (`ops_daily_spend`, `ops_user_daily_usage`), kill-switch procedure (`user_limits` insert/delete with `note`), spend-threshold tuning (workflow env)

**Checkpoint**: US1 fully functional — load test + budget exhaustion + cost view + kill switch all verifiable locally

---

## Phase 4: User Story 2 — User data is private and recoverable (Priority: P1)

**Goal**: Paid-tier switch proven config-only; nightly graph export to durable access-controlled storage with alert-on-miss; restore runbook written and rehearsed

**Independent Test**: quickstart.md US2 — tier switch with zero code diff; dated export in the bucket; deliberate workflow failure alerts; restore rehearsal on a scratch instance matches independent counts

### Tests for User Story 2 (write first, ensure they FAIL)

- [x] T024 [P] [US2] Export/restore round-trip test in `api/tests/test_export_restore.py`: export against the fake graph store → JSON document shape per data-model.md (independent `counts` aggregation vs row dump), restore into an empty fake store → counts and spot-checked properties match; malformed-artifact restore fails loudly without partial writes
- [x] T025 [P] [US2] Storage-upload unit test in `api/tests/test_export_upload.py`: correct bucket/object name `graph-export-YYYY-MM-DD.json`, service-role auth header, upload failure exits non-zero (drives the workflow alert)

### Implementation for User Story 2

- [x] T026 [US2] Implement `api/scripts/export_graph.py`: serialize all v1-schema nodes/relationships via the existing Neo4j driver config, write the data-model.md JSON document (independent counts query), upload to private `graph-exports` bucket via `httpx` + Supabase Storage REST, final freshness assertion (today's object exists, non-empty) (depends on T024, T025)
- [x] T027 [US2] Implement `api/scripts/restore_graph.py`: load a named artifact, replay nodes then relationships into an **empty** target instance (refuse non-empty unless `--force-empty-check-off`), report counts vs the artifact's `counts` and exit non-zero on mismatch
- [x] T028 [P] [US2] Create workflow `.github/workflows/nightly-export.yml`: nightly cron + `workflow_dispatch`, runs `export_graph.py` with `NEO4J_*`/`SUPABASE_*` repo secrets; any failure → GitHub failure email (research.md R5); doubles as the Aura keep-alive touch
- [x] T029 [P] [US2] Write `docs/runbooks/restore.md`: prerequisites (scratch Aura instance), exact commands, spot-check queries, rehearsal-date log line (SC-003 requires one rehearsal before first invite)
- [x] T030 [P] [US2] Document the config-only tier switch in `docs/runbooks/operations.md` (new section): paid-key swap steps on Render, free-key removal same day, zero-code-diff verification step (research.md R3, Constitution VI proof)
- [ ] T031 [US2] **[HUMAN]** Execute the paid-tier switch: create billing-enabled Google Cloud project, mint paid Gemini key, swap `GOOGLE_API_KEY` on Render, remove free key; record in `docs/getting-started.md` — **top priority while the pilot runs (2026-10-11)**: pilot users' conversations are currently under free-tier terms
- [x] T032 [US2] **[HUMAN]** Add `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` as GitHub repo secrets; enable the two workflows; verify first scheduled export lands in the bucket -- done 2026-08-26: secrets set via `gh secret set`, `005-hardening-and-pilot` merged to `main` (workflows only run scheduled off the default branch), `nightly-export.yml` triggered via `workflow_dispatch` after an Aura auto-pause delay, confirmed live in the `graph-exports` bucket (`graph-export-2026-08-26.json`, 154 nodes/167 relationships, 68449 bytes)
- [x] T033 [US2] Execute the restore rehearsal per `docs/runbooks/restore.md` against a scratch instance using a real nightly artifact; record date + counts in the runbook (SC-003; blocked on T032) -- done 2026-08-26 against a local Neo4j (Docker) scratch instance (Aura Free is 1/account); found + fixed 2 real bugs (Date/Time serialization losing type info, a deserialization error causing a partial write) before it passed clean; see `docs/runbooks/restore.md`'s rehearsal log

**Checkpoint**: A real dated export exists nightly, a missed export emails, and restore has been proven once

---

## Phase 5: User Story 3 — Voice failure states are honest (Priority: P2)

**Goal**: Every cell of the seven-cell matrix (research.md R9) ends in a specific named state with a remedy and a working chat path; unsent input survives connectivity loss

**Independent Test**: quickstart.md US3 — walk the matrix on both platforms; every cell shows the specific state, composer never disabled

### Tests for User Story 3 (write first, ensure they FAIL)

- [x] T034 [P] [US3] Extend `app/src/hooks/use-voice-session.test.ts`: state transitions for V2 (permission revoked mid-session → guidance state), V5 (network error mid-recognition → interim transcript preserved to composer), V7 (abort/interruption → clean stop, partial preserved, resumable); composer-enabled invariant asserted in every failure state
- [x] T035 [P] [US3] Unit tests for offline send in a new `app/src/hooks/use-chat-session.test.ts`: V4 — send while offline keeps text, marks message failed with retry affordance, reconnect triggers auto-send exactly once; retry after explicit failure works
- [x] T036 [P] [US3] Unit tests for TTS failure in `app/src/lib/voice-capabilities.test.ts` (extend): V6 — Speech error → spoken-replies marked unavailable, no throw
- [x] T037 [P] [US3] Playwright web-drivable cells in `app/e2e/playwright/voice-failures-005.spec.ts`: V4 offline compose→reconnect→send (context offline emulation), V1/V3 guidance states render with chat path (mocked capability probe)
- [x] T038 [P] [US3] Maestro flow for device cells where scriptable in `app/.maestro/voice-failures-005.yaml` (V2 revoke-return where the platform allows; otherwise the flow asserts the recovery screen after a forced error); remaining cells (V6, V7, true mid-call focus loss) explicitly deferred to the manual matrix (T063)

### Implementation for User Story 3

- [x] T039 [US3] Extend `app/src/hooks/use-voice-session.ts`: named failure states for V2/V5/V7 mapped from recognizer error codes (permission, network, aborted/audio-focus), interim-transcript preservation into the composer, resume affordance (depends on T034)
- [x] T040 [US3] Extend `app/src/hooks/use-chat-session.ts` + `app/src/lib/api.ts`: V4 offline detection via `@react-native-community/netinfo`, unsent-input preservation, failed-marker + retry, auto-send-on-reconnect (single-flight) (depends on T035)
- [x] T041 [US3] Extend TTS handling for V6 in `app/src/lib/voice-capabilities.ts` and the session screen `app/src/app/(main)/skill/[id]/session.tsx`: Speech error → text-only banner state, spoken-replies toggle shows unavailable (depends on T036)
- [x] T042 [P] [US3] Add all new voice-failure strings (V2/V4/V5/V6/V7 names + remedies + banner copy) to `app/src/i18n/locales/{en,hi,es,fr,de}.json` — each names the problem and the remedy (US3 scenario 1)

**Checkpoint**: Matrix walkable; web cells automated, device cells scripted or queued for the manual matrix

---

## Phase 6: User Story 4 — The operator can see what's happening (Priority: P2)

**Goal**: SC-005's three numbers from dashboards alone; structured AI-failure logs tied to endpoint/pseudonymous-user/intent; push outcomes observable; health alert

**Independent Test**: quickstart.md US4 — generate known traffic; each event appears in `ops_*` views / structured logs with debuggable context and zero transcript leakage

### Tests for User Story 4 (write first, ensure they FAIL)

- [x] T043 [P] [US4] Emission-seam tests: extend `api/tests/test_chat_contract.py` (chat turn emits `session_started` on session boundary; validation-retry exhaustion emits `intent_validation_failed` with endpoint+attempts), `api/tests/test_session_summary.py` (summarize emits `session_ended` with message_count), `api/tests/test_notifications.py` (send path emits `push_sent`/`push_failed` mirroring the delivery log); all assert analytics failure never fails the request
- [x] T044 [P] [US4] Log-redaction test in `api/tests/test_log_redaction.py`: drive a chat turn with a sentinel string through the app with `caplog`; assert no log record contains the sentinel, the API key, or the JWT; assert the `ai_failure` event carries endpoint, sub, intent type, failure class (research.md R14)

### Implementation for User Story 4

- [x] T045 [US4] Emit analytics at the seams (plan.md note 5): `session_started`/`intent_validation_failed` in `api/src/skillcoach_api/routes/chat.py`, `session_ended` in `api/src/skillcoach_api/services/session_summary.py`, `push_sent`/`push_failed` in `api/src/skillcoach_api/services/notifications.py` (depends on T043)
- [x] T046 [US4] Add the structured `ai_failure` log helper to `api/src/skillcoach_api/logging_setup.py` and call it from the LLM failure paths in `api/src/skillcoach_api/routes/chat.py` / `api/src/skillcoach_api/services/llm.py` (endpoint, sub, intent type, failure class — never bodies) (depends on T044)
- [x] T047 [P] [US4] Create workflow `.github/workflows/healthcheck.yml`: every 30 min + `workflow_dispatch`, curl the deployed `/health`, fail on non-200/timeout (research.md R6)
- [x] T048 [P] [US4] Extend `docs/runbooks/operations.md`: logging policy text (FR-007), SC-005 query cookbook (`ops_daily_sessions`, `ops_retention`, `ops_intent_failure_rate`, `ops_push_outcomes`) with example output, Render log search guide, weekly external-limits review checklist (research.md R15) with a dated log table
- [x] T049 [US4] Validate all three alert emails per quickstart (deliberate failure of spend-check, nightly-export, healthcheck via `workflow_dispatch`); record dates in `docs/runbooks/operations.md` (blocked on T022, T028, T032, T047) -- done 2026-08-26: all 3 workflows deliberately failed via input overrides (no real secrets touched), owner confirmed all 3 GitHub failure emails received; found + documented a real caveat (spend-check's strict `>` needs a negative threshold_override to force failure when real spend is $0)

**Checkpoint**: Known traffic → visible numbers + searchable structured failures; alerts proven

---

## Phase 7: User Story 5 — Strangers can install and start unaided (Priority: P1, capstone)

**Goal**: Warm host live; TestFlight/Play internal distribution per runbook; onboarding explains push-to-talk + notifications with contextual permissions; Sign in with Apple; deletion entry + operator deletion runbook; pilot cohort tracked against the exit bar

**Independent Test**: quickstart.md US5 — a fresh-device stranger installs via beta channel and completes a session with zero intervention; latency p90 < 3 s warm

### Tests for User Story 5 (write first, ensure they FAIL)

- [x] T050 [P] [US5] Unit tests for onboarding gating in `app/src/__tests__/onboarding-welcome.test.tsx`: shown once post-signup, skippable, never re-shown after completion, notification permission requested only from the explainer action (research.md R12)
- [x] T051 [P] [US5] Playwright onboarding + deletion entry in `app/e2e/playwright/onboarding-005.spec.ts`: first-run explainer cards appear and complete into the dashboard; Settings → Delete account opens the configured URL (link/`window.open` asserted, not followed)
- [x] T052 [P] [US5] Unit test for operator deletion in `api/tests/test_delete_user.py`: against fake stores — user's graph subgraph fully detach-deleted (scoped to that user only, second user untouched), Supabase rows removed per runbook order, non-existent user is a safe no-op

### Implementation for User Story 5

- [x] T053 [P] [US5] Create first-run explainer `app/src/app/(onboarding)/welcome.tsx`: 2–3 cards (push-to-talk, notifications), contextual "enable nudges" permission action reusing `app/src/lib/push-notifications.ts`, completion flag in AsyncStorage + routing from `app/src/app/index.tsx` (depends on T050)
- [x] T054 [P] [US5] Add Sign in with Apple to `app/src/app/(auth)/sign-in.tsx` via `expo-apple-authentication` + existing Supabase auth session flow in `app/src/lib/oauth.ts` (iOS-only render; research.md R11)
- [x] T055 [P] [US5] Add "Delete account" row to `app/src/app/(main)/settings.tsx` opening `EXPO_PUBLIC_DELETE_ACCOUNT_URL` (fallback to existing policy URL) in the system browser (research.md R13)
- [x] T056 [P] [US5] Implement `api/scripts/delete_user.py`: parameterized per-user detach-delete (graph), Supabase auth-user + rows deletion, confirmation prompt + dry-run flag (depends on T052)
- [x] T057 [P] [US5] Add onboarding/auth/deletion strings to `app/src/i18n/locales/{en,hi,es,fr,de}.json`
- [x] T058 [P] [US5] Change `render.yaml` `plan: free` → `plan: starter` with a comment marking it the Constitution-IX sanctioned spend (research.md R4)
- [x] T059 [P] [US5] Write `docs/runbooks/release.md` (local Xcode archive → TestFlight; local `gradlew bundleRelease` → Play internal; versioning, signing, tester management), `docs/runbooks/deletion.md` (operator deletion per R13 incl. export-retention note), and `docs/runbooks/pilot.md` (roster table, invite flow, `ops_pilot_exit_bar` query, issue-triage log)
- [ ] T060 [US5] **[HUMAN]** Execute flagged enrollments & switches: Render Starter upgrade, Apple Developer Program (~$99/yr), Play Console ($25), Supabase Apple-provider config; record each in `docs/getting-started.md` — **Split 2026-10-11**: Render Starter is needed for the pilot now. Apple Developer Program, Play Console and the Supabase Apple-provider config are **deferred to post-pilot** (the pilot runs on web + private APK)
- [ ] T061 [US5] Execute `docs/runbooks/release.md` once per platform: TestFlight build visible to an internal tester, Play internal install link works; latency check — 20 scripted turns on the warm host, `duration_ms` p90 on `POST /v1/chat` < 3000 per the operations.md query (blocked on T060; research.md R10) — **Deferred to post-pilot (2026-10-11)** except the latency check, which can run during the pilot once Render Starter is on

**Checkpoint**: An invited stranger can install and start unaided; pilot can begin

**Pilot channel (2026-10-11)**: the pilot is running on the web UI (Render
Static Site) plus a privately distributed Android release APK, without the
store channels this checkpoint assumed. Store distribution (TestFlight, Play
internal) moved to a post-pilot release. See `docs/getting-started.md` → "Pilot
channel (current)".

---

## Phase 8: Polish & Cross-Cutting Concerns

- [x] T062 [P] Restore CI: `.github/workflows/ci.yml` running api lint (`ruff`) + `pytest` and app `npm test` on push (deferred-from-001 item, `docs/getting-started.md`)
- [x] T063 Update `docs/testing.md` with the 005 section: automated-test index mapped to FRs/ACs/edge cases + manual checklist (voice matrix device cells V2/V6/V7 per platform, real beta installs, alert-email proofs, restore rehearsal) — exit-gate requirement, Constitution VIII
- [x] T064 Update `docs/getting-started.md`: mark executed spend rows with dates, remove satisfied items, add the operational secrets inventory (GH repo secrets)
- [ ] T065 Execute quickstart.md end-to-end (US1–US5 sections + FR-011/R15 live-console verification checklist); record results + console numbers in quickstart exit notes — **scope during the pilot (2026-10-11)**: web + Android. Mark iOS-native cells (TestFlight, APNs push, Sign in with Apple) as not covered until the post-pilot store release
- [ ] T066 Pilot exit review against SC-001–SC-005: `ops_pilot_exit_bar` per pilot user ≥3 sessions, zero raw-error scan of logs, cost within envelope, triaged backlog recorded in `docs/runbooks/pilot.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)** → **Foundational (Phase 2)** → user stories
- **US1 (Phase 3)**: after Foundational; no story dependencies
- **US2 (Phase 4)**: after Foundational; independent of US1 (T031/T032 are human gates)
- **US3 (Phase 5)**: after Setup only (client-side; T002 for netinfo) — can run parallel to US1/US2
- **US4 (Phase 6)**: after Foundational; T043/T045 touch chat/notifications seams also touched by US1 (T016/T017) — run after US1 or coordinate; T049 needs US1's and US2's workflows
- **US5 (Phase 7)**: capstone — T061 needs the warm host + release runbook; onboarding/deletion/auth tasks (T050–T057) only need Setup and can start anytime
- **Polish (Phase 8)**: T063–T066 need all stories; T062 anytime

### Key task-level dependencies

- T004 (migration) blocks T009, T010, T015 (user_limits/token RPC), T043, T045 (analytics table)
- T013 + T014 → T015 → T016/T017 → T018
- T024/T025 → T026 → T027 → T028; T032 → first real export → T033
- T049 blocked on T022 + T028 + T032 + T047
- T060 blocks T061; T031/T032/T060 are **[HUMAN]** gates the agent stops at and reports

### Parallel Opportunities

- Phase 1: T002 ∥ T003 (after T001)
- Phase 2: T005 ∥ T006 after T004
- US1 tests T008–T012 all ∥; then T013 ∥ T014, T019–T023 all ∥ after T017
- US2 T024 ∥ T025; T028–T030 all ∥ after T027
- US3 tests T034–T038 all ∥; T042 ∥ implementation
- US5 T050–T052 ∥; T053–T059 largely ∥ (distinct files)
- Cross-story: US3 (client) ∥ US1/US2 (backend/ops) with different files throughout

---

## Parallel Example: User Story 1

```bash
# Launch all US1 tests together (write first, watch them fail):
Task: "Unit tests for the queue in api/tests/test_llm_queue.py"
Task: "Extend api/tests/test_budget.py for override/blocked/report"
Task: "Extend api/tests/test_chat_contract.py for the 200 budget turn"
Task: "Unit tests for spend check in api/tests/test_spend_check.py"
Task: "Playwright budget bubble in app/e2e/playwright/budget-005.spec.ts"

# Then the two independent implementation roots:
Task: "Implement LlmQueue in api/src/skillcoach_api/services/llm_queue.py"
Task: "Extend BudgetExceeded in api/src/skillcoach_api/models/errors.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phases 1–2 (setup + migration + analytics service)
2. Phase 3 (US1) → **STOP and VALIDATE**: load sim + budget exhaustion + cost views locally — the product is now safe to put load on, which gates everything else

### Incremental Delivery

1. US1 → deploy: uncontrolled-cost risk closed (the pilot's hardest blocker)
2. US2 → data is recoverable + paid-terms private; alerts live
3. US3 ∥ US4 → honest voice states; operator eyes
4. US5 → distribution + onboarding; **human executes spend gates**; invite pilot cohort
5. Phase 8 exit review closes the feature against SC-001–SC-005

### Human-gate summary (Constitution IX)

| Task | Spend | Unblocks |
|------|-------|----------|
| T031 | Gemini paid tier (usage-based) | pilot-grade privacy terms (US2) |
| T032 | $0 (secrets) | nightly export + restore rehearsal |
| T060 (pilot) | Render Starter ~$7/mo | warm host, pilot latency (SC-004) |
| T060 (post-pilot) | Apple $99/yr, Play $25 | store beta channels (US5); deferred 2026-10-11 |

---

## Notes

- Every FR maps to tasks: FR-001→T008–T018, FR-002→T030/T031, FR-003→T020/T022/T023, FR-004→T058/T060/T061, FR-005→T024–T033, FR-006→T034–T042, FR-007→T043–T048, FR-008→T043/T045/T048, FR-009→T050–T061, FR-010→T059/T066, FR-011→T048/T065, FR-012→T051/T055/T056/T059
- Spec edge cases: cost spike/kill switch→T009/T015/T023; node ceiling watch→T048; backup access control→T004 (private bucket)/T029; deletion request→T055/T056/T059
- Verify tests fail before implementing; commit after each task or logical group (on the feature branch, per the branch-per-feature workflow)
