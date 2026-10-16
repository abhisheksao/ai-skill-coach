# Testing — Regression Catalog

Required by Constitution Principle VIII (Testing Discipline) / Amendment 1.7.0:
a maintained, human-executable index of every automated test plus a checklist
of scenarios not yet automated. Update this file at every feature's exit gate
— it's part of "done," not a follow-up task.

## How to run

**Backend** (`api/`):
```bash
cd api && uv run ruff check . && uv run pytest        # full suite + lint
uv run pytest -m foundations                            # feature 001 only
uv run pytest -m wizard_plan                             # feature 002 only
uv run pytest -m voice_layer                             # feature 003 only
uv run pytest -m progress_notifications                  # feature 004 (+ some shared-file 002 tests, see below)
uv run pytest -m hardening                               # feature 005 (queue, budget turn, export/restore, analytics, ops)
uv run pytest -m chat                                    # one workflow across all five features
```
Full marker list (feature + workflow): `api/pyproject.toml` under `[tool.pytest.ini_options].markers`.
`--strict-markers` is on, so a typo'd `-m` expression fails loudly instead of silently running 0 tests.

**Web E2E** (`app/`):
```bash
npm run e2e:seed   # once: ensures the 2 Playwright test accounts + their profiles exist
npm run e2e        # builds (--clear, see Gotchas below) + serves + runs the suite
```
Runs against the live deployed API/Supabase/Aura — real Gemini calls, real quota.

**Native E2E** (`app/`): `maestro test .maestro/flows/<name>.yaml` against a connected
device/emulator (needs the Maestro CLI + `.maestro/.env`, copy from `.env.example`).
Flows currently in the repo are written but **not yet verified on-device** — see
the E2E harness section below.

**Manual**: full scripted walkthroughs live in each feature's own quickstart —
`specs/001-foundations/quickstart.md`, `specs/002-wizard-and-plan/quickstart.md`.
The checklist below pulls forward only what those runs left un-automated.

### Gotchas found while building this suite

- `expo export --platform web` can silently ship a build with a **stale
  Metro-cached** transform holding empty `EXPO_PUBLIC_SUPABASE_*` values, even
  though the CLI reports loading/exporting the real `.env` vars. `npm run
  e2e:build` now passes `--clear` for this reason — don't drop it.
- The live API's `CORS_ORIGINS` must include whatever port the E2E web build is
  served on (`http://localhost:4021` by default — see `playwright.config.ts`'s
  comment on why that port specifically). Already set in `render.yaml` + local
  `api/.env`; if you ever change the port, update both.
- PW1/PW2 (`app/e2e/playwright/fixtures/test-users.ts`) share the same
  `DAILY_LLM_BUDGET` (50/user/day) as any other account. Running the full
  wizard/regenerate suite repeatedly in one day **will** exhaust it — spread
  load across PW1/PW2, or wait for the daily reset (UTC).

## Status summary (2026-07-25)

- 362 automated backend tests (unit + API contract): 78 tagged `foundations`
  (001), 108 tagged `wizard_plan` (002), 5 tagged `voice_layer` (003), 114
  from 004 (progress/notifications/dashboard/check-ins/session-continuity/
  goal-revision fixes), and 56 tagged `hardening` (005 — queue/budget-turn/
  spend-check/export-restore/analytics/log-redaction/delete_user, see the
  new index section below). All green as of last run (`uv run pytest -q`).
- 58 app unit tests (jest, pure logic — `voice-capabilities.ts`,
  `use-voice-session.ts`'s exported helpers, `push-notifications.ts`,
  `dashboard-cache.ts`, and (005) `resolveOnboardingRedirect` +
  `requestPushPermissionAndRegister`; this app has no component-rendering
  test library, see the jest table below).
- Playwright has real scenario coverage for all five features (17 specs).
  **Re-run live in full 2026-07-25**: 24/27 test cases passed against the
  deployed stack (workers:1, one full pass). The 3 failures were
  `progress-checkins.spec.ts` (×2) and `voice.spec.ts`'s push-to-talk send
  test, all failing on a live `429` from the shared PW1 test account
  hitting `DAILY_LLM_BUDGET` — a byproduct of this session's own heavy
  repeated testing (see `docs/testing.md`'s Gotchas above), not a code
  regression: `wizard-plan.spec.ts`'s real wizard/LLM flows immediately
  before them in the same run passed cleanly. This finally reconfirms
  004's `notifications-deep-link.spec.ts` and `dashboard.spec.ts` live
  (previously "written, not yet run" — see the corrected 004 checklist
  items below); `progress-checkins.spec.ts` needs a clean re-run after
  the next UTC daily budget reset to get the same confirmation.
  005 added 3 new specs, all passing live in this run: `budget-005.spec.ts`,
  `onboarding-005.spec.ts` (3/3, see the two real bugs it caught below),
  `voice-failures-005.spec.ts`.
- Maestro has five scenario flows beyond the original smoke test (three
  `voice-*.yaml` from 003, run live 2026-07-17 on Android; `session-
  persists.yaml` from 001, confirmed manually 2026-08-27 on iOS — see
  below, not yet a green Maestro CLI run on either platform;
  `voice-failures-005.yaml` from 005, **written, not yet run on-device**).
  004 added no new Maestro flows.
- Multilingual sampling (Constitution VIII) is complete for 001, 002, and
  003 (EN+HI full, ES/FR/DE smoke; 003's native permission-prompt strings
  localized via `expo.locales`, visually confirmed live on iOS 2026-08-27,
  Android still unconfirmed). 004's strings are translated in all 5
  languages but not visually sampled live. 005's new strings (budget-
  exhausted reply, 7 voice-failure states, onboarding cards, Apple
  sign-in, delete account) are translated in all 5 locale files and spot-
  checked programmatically (`en`/`hi`/`es`/`fr`/`de` key parity confirmed
  2026-07-25) but not yet visually sampled live on-device.
- **iOS device session, 2026-08-27**: first-ever physical iOS device
  testing for this project (a personal, non-paid Apple Developer team —
  see manual checklist item 23 for the entitlements/autolinking fix this
  required). Confirmed live on an iPhone 16: sign-up + profile flow,
  session persistence, full voice layer (STT/TTS/push-to-talk/permission-
  denial — previously Android-only), native permission-prompt
  localization across all 5 languages, and the Sign-in-with-Apple /
  push-notification-prompt soft-fail behavior that fix intentionally
  produces. Real Sign in with Apple and real push delivery on iOS remain
  blocked on T060 (paid Apple Developer Program).

## Automated test index

### Feature 001 — Foundations (`pytest -m foundations`, 78 tests)

| File | Workflow marker | Covers |
|---|---|---|
| `test_smoke.py` | smoke | App boots (FastAPI TestClient) |
| `test_health.py` | smoke | `GET /health` needs no auth |
| `test_config.py` | config | Settings/env parsing, CORS origin list, git-sha resolution |
| `test_container.py` | container | DI container wiring — services share the right client/driver instances |
| `test_auth.py` | auth | JWT verification: valid/expired/garbage/missing token, wrong audience, JWKS fetch failure |
| `test_supabase_rest.py` | supabase | PostgREST client: insert/upsert/select/rpc, and all their error-response paths |
| `test_profiles_store.py` | profile | `ProfileStore` upsert row-building + REST-returns-none fallback |
| `test_profile_models.py` | profile, models | Profile payload Pydantic validation incl. consent/timezone/language rejects |
| `test_profile_contract.py` | profile | `POST /v1/profile` contract tests 3–4, auth requirement, graph-failure-still-200 |
| `test_budget.py` | budget | `BudgetGuard` allows/blocks at the daily cap |
| `test_graph.py` | graph | `GraphService.ensure_user` MERGE, failure-tolerant (never raises), certifi TLS downgrade |
| `test_messages.py` | messages | `MessageStore` insert/read/count, skill_id stamping, REST-failure propagation |
| `test_logging_setup.py` | logging | JSON log formatter, request-id middleware, idempotent setup |
| `test_tenancy.py` | tenancy | Identity comes from JWT not body; two tokens never cross-write; migration blocks client writes |

### Feature 002 — Wizard & Plan (`pytest -m wizard_plan`, 108 tests)

| File | Workflow marker | Covers |
|---|---|---|
| `test_chat_models.py` | chat, models | `ChatRequest`/`ChatTurn` bounds, `suggested_replies` cap |
| `test_chat_contract.py` | chat | `/v1/chat` contract 5–7, wizard-vs-coaching-turn routing, `suggested_replies` pass-through, skill_id resolution on wizard completion |
| `test_chat_wizard.py` | chat, wizard | 12-turn cap forces summarize, atomicity through the real route, validation-exhaustion degrades gracefully — wired with real services, fakes only at the I/O boundary |
| `test_llm.py` | llm | Provider retry/backoff, validation-failure retry-with-feedback (max 2) then graceful degrade, regenerate reason/note/force_different reach the prompt, wizard date/suggested-replies instructions |
| `test_prompts.py` | prompts | Wizard/coaching/regenerate system-prompt builders, language fallback |
| `test_intent_models.py` | intents, models | 4 intent schemas incl. discriminated-union dispatch/rejection, field bounds |
| `test_intent_apply.py` | intents | `apply_intents` atomicity (all-or-nothing), `create_skill`+`create_plan` together, `revise_goal`/`revise_plan` SUPERSEDES scoping |
| `test_context_builder.py` | context | Context assembly scoped to session/skill, missing-or-not-owned skill returns `None` not a crash, provider-failure propagation |
| `test_plan_similarity.py` | plan | difflib similarity guard: identical/reordered/reworded vs. meaningfully different plans |
| `test_skills_models.py` | skills, models | Regenerate-reason payload validation |
| `test_skills_service.py` | skills | `SkillsService` list/get, ordered steps + derived generation number, graph-failure propagation |
| `test_skills_contract.py` | skills, regenerate | `/v1/skills` + `/v1/skills/{id}`, regenerate happy-path/cap-409/similarity-retry/reason-reaches-llm/404/auth |
| `test_skill_isolation.py` | skills, tenancy | Two same-named skills never cross-contaminate — regression test for the real name-matching bug found in 002 Phase 4 |

### Feature 003 — Voice Layer (`pytest -m voice_layer`, 5 tests)

| File | Workflow marker | Covers |
|---|---|---|
| `test_chat_contract.py::test_modality_{defaults_to_chat,voice_persists}` | chat | `ChatRequest.modality` round-trips through `MessageStore.insert_turn` — previously hardcoded to `"chat"` despite the column existing since 001 |
| `test_chat_wizard.py::test_modality_never_affects_llm_prompt_or_context` | chat, wizard | Constitution IV invariant: two otherwise-identical requests differing only in `modality` produce a byte-identical LLM prompt/context, proven through the real route with a `FakeRunnable` that records what it was called with |
| `test_profile_contract.py::test_voice_replies_enabled_{defaults_to_true,false_persists}` | profile | `voice_replies_enabled` round-trips through `POST /v1/profile`, defaults to `true` |

### Feature 004 — Progress & Notifications (114 new tests)

Wholly-new files (every test in these is 004-specific):

| File | Domain marker | Covers |
|---|---|---|
| `test_progress.py` | progress | `ProgressService`: completed steps, streak (same-day dedup, broken-then-resumed run), per-step behind-cadence boundary at exactly `CADENCE_BEHIND_MULTIPLIER`, backdated-`timestamp` case uses `timestamp` not `created_at` |
| `test_cadence_schedule.py` | cadence | `CadenceScheduleService.sync`: delete-all-then-insert-current (trivially handles a shrinking step list), `all_rows()` fan-out read |
| `test_notifications.py` | notifications | Push-token lifecycle, frequency cap (per-skill-per-day + per-user-per-week) at boundary, quiet-hours incl. a real non-UTC timezone, `send_cadence_nudge`'s full outcome matrix, 3-skills-behind-at-once Edge Case, 21-day multi-week cap simulation (SC-004) |
| `test_notifications_contract.py` | notifications | `POST`/`DELETE /v1/push-tokens` incl. re-registration covering token rotation (FR-013), internal-secret 401/200 for both cron routes |
| `test_session_summary.py` | sessions | `SessionSummaryService`: eligible-session summarize+write, already-summarized skip, no-messages skip, one session's LLM failure never blocks another (FR-006 scenario 3), cutoff passed to the SQL RPC |
| `test_chat_checkins.py` | chat, checkins | `log_checkin`/`complete_step`/`report_obstacle` applied end-to-end through the real `/v1/chat` route; step_order outside the active plan rejected |
| `test_progress_contract.py` | progress, dashboard | `GET /v1/skills/{id}/progress` shape/drift-free-repeat/404/auth; `GET /v1/dashboard` shape, per-step list, staleness flag + boundary, agreement with the per-skill endpoint (SC-006), zero-skills empty response |
| `test_checkins_contract.py` | checkins | `POST /v1/intents/apply`: happy path, `source` always `ui_tap` regardless of request body (FR-016), `report_obstacle` rejected (conversation-only), validation failure has no retry (FR-015), zero-LLM-call proof (no `llm`/`budget` on the fake services container at all), double-tap produces two independent CheckIns |

Extended files (only the new/changed tests are 004's; the rest predate it):

| File | What 004 added |
|---|---|
| `test_intent_apply.py` | `log_checkin`/`complete_step`/`report_obstacle` Cypher translation, `valid_step_orders` guard, backdated-timestamp preservation, `checkin_id` on `ApplyResult`; regression test for the `_REVISE_PLAN` goal-linking bug (US5) |
| `test_context_builder.py` | Gap description when a step is behind cadence, recent session summaries, goal revision history — all only populated when a skill is active |
| `test_prompts.py` | `build_coaching_prompt`'s gap-note, session-history-note, and goal-trajectory-note (each independently on/off) |
| `test_skills_service.py` | `recent_session_summaries`, `goal_revision_history` (oldest-first, current last) |
| `test_container.py` | New services wired with the right shared driver/rest/budget/llm instances |
| `test_supabase_rest.py` | `update()`/`delete()`, `select_many`'s `raw_filters` |
| `test_chat_wizard.py` | cadence-sync-not-triggered-by-a-checkin-alone regression |
| `test_skill_isolation.py` | Fixture updates only (new `ContextBuilder` dependencies) |

### Feature 005 — Hardening & Pilot (`pytest -m hardening`, 56 tests)

| File | Domain marker | Covers |
|---|---|---|
| `test_llm_queue.py` | queue | `LlmQueue`: FIFO admission order, concurrency cap, token-bucket pacing (fake clock, no real sleeps), `LLM_QUEUE_MAX_WAIT_SECONDS` exceeded raises `LlmUnavailable` |
| `test_spend_check.py` | ops | `spend_check.py`: under-threshold exits 0, over-threshold exits non-zero, missing view data handled |
| `test_export_restore.py` | ops | Export/restore round-trip against a fake graph store: JSON shape matches data-model.md, independent counts aggregation, restore into an empty store matches, malformed artifact fails loudly with no partial writes |
| `test_export_upload.py` | ops | Storage upload: correct `graph-export-YYYY-MM-DD.json` object name, service-role auth header, upload failure exits non-zero |
| `test_analytics.py` | analytics | `AnalyticsService.emit`: successful insert, insert-failure swallowed (never raises), `properties` never contains a message-body key |
| `test_log_redaction.py` | logging | A sentinel string driven through a real chat turn never appears in any log record, the API key, or the JWT; `ai_failure` event carries endpoint/sub/intent-type/failure-class only |
| `test_delete_user.py` | ops | Operator deletion against fake stores: full subgraph detach-delete scoped to one user, every Postgres table incl. `analytics_events` (keyed by `user_sub`, not `user_id`), second user never touched, non-existent user is a safe no-op, auth-delete 404 treated as already-gone |
| `test_budget.py` (extended) | budget | Over-budget raises before queueing, `daily_budget_override` honored (0 = paused), `blocked=true` raises immediately, `report()` records tokens via `record_llm_tokens`, missing `user_limits` row means defaults |
| `test_chat_contract.py` (extended) | chat, budget | Budget-exhausted chat returns 200 with `errors.budget_exhausted_reply` + `budget.exhausted`/`resets_at`, zero LLM invocations, turn persisted; blocked user gets the same shape without `resets_at`; `session_started`/`intent_validation_failed` analytics emission |
| `test_session_summary.py` (extended) | sessions, analytics | `session_ended` analytics emission with `message_count` |
| `test_notifications.py` (extended) | notifications, analytics | `push_sent`/`push_failed` analytics mirroring the delivery log |
| `test_container.py` (extended) | container | `AnalyticsService`/`LlmQueue` wired with the right shared instances |

### App additions — `app/src/` (005)

| File | Covers |
|---|---|
| `hooks/use-voice-session.test.ts` (extended) | V2 permission-revoked-mid-session guidance state, V5 network-error-mid-recognition interim-transcript preservation, V7 abort/interruption clean-stop-and-resume; composer-enabled invariant asserted in every failure state |
| `hooks/use-chat-session.test.ts` (new) | V4 offline send: text preserved, message marked failed with retry affordance, reconnect triggers auto-send exactly once, retry-after-failure works |
| `lib/voice-capabilities.test.ts` (extended) | V6 TTS Speech-error marks spoken-replies unavailable without throwing |
| `__tests__/onboarding-welcome.test.tsx` (new) | `resolveOnboardingRedirect`'s full state machine incl. a regression case for the real profile→welcome routing bug found live (see below); `requestPushPermissionAndRegister`'s contextual-only escalation; `isWelcomeSeen`/`markWelcomeSeen` persistence |

**Two real bugs found via live Playwright replay, not caught by the unit
tests above** (the first was actually encoded as *expected* behavior in
the original test, since it only exercised the pure function with
hand-picked inputs that happened to avoid the failure mode):

1. `resolveOnboardingRedirect` checked only the top-level route group
   (`segments[0]`). `/profile` and `/welcome` both live under the
   `(onboarding)` group, so the function couldn't distinguish "still on
   `/profile`, must advance to `/welcome`" from "already on `/welcome`,
   stay put" — a user finishing the profile step was permanently
   stranded there. Fixed to check the full segment path
   (`app/src/lib/onboarding.ts`).
2. `_layout.tsx` cached `welcomeSeen` in component state fetched once on
   mount. `welcome.tsx`'s `finish()` writes the flag to AsyncStorage then
   does a plain `router.replace('/dashboard')` — with no equivalent of
   `AuthContext`'s `refreshProfile()` to push the new value back up, the
   gate's redirect effect re-ran with the stale cached `false` and
   immediately bounced back to `/welcome` (freshly remounted, reset to
   its first card). Fixed by re-reading AsyncStorage on every navigation-
   relevant change instead of caching (`app/src/app/_layout.tsx`).

Both confirmed fixed via a live rebuild + re-run of
`onboarding-005.spec.ts` (3/3 passing) — see git history on
`005-hardening-and-pilot` for the full commit.

### App unit tests (jest) — `app/src/`

No `@testing-library/react(-native)` is installed in this project — jest
covers pure logic and hook state machines (via a manual
`react-test-renderer` harness, documented in the test file itself), not
rendered component output. UI behavior lives in the Playwright/Maestro
tables below instead.

| File | Covers |
|---|---|
| `lib/voice-capabilities.test.ts` | STT/TTS availability detected and degrading **independently** per language (clarified FR-007); `resolveMicDisabledReason` combining capability + permission state |
| `hooks/use-voice-session.test.ts` | `shouldPromptConfirmation`/`resolveInterimMode` pure helpers (FR-002/003 clarified); `speak()`/`stopSpeaking()`; `start()`'s unconditional TTS-interrupt-before-record (US2 scenario 2); contextual permission request (`getPermissionsAsync` every call, `requestPermissionsAsync`'s OS dialog only when undetermined); the web-specific `"not-allowed"` error-event fallback (a real gap found via package source inspection — `expo-speech-recognition`'s permission-check methods are no-ops on web) |
| `lib/push-notifications.test.ts` | `resolvePushPlatform` (RN `Platform.OS` → API enum); `extractSkillIdFromNotificationData` defensive against malformed/foreign payloads — both extracted from `hooks/use-push-notifications.ts` into this file since the hook transitively imports `lib/supabase.ts` → AsyncStorage, unmocked in this project's jest setup |
| `lib/dashboard-cache.test.ts` | Read/write/overwrite round-trip for the offline stale-data fallback (research.md R10) — `jest.mock`'s the official `@react-native-async-storage/async-storage` jest mock, scoped to this file only |

## E2E harness

### Playwright (web) — `app/e2e/playwright/tests/`

| Spec | Covers |
|---|---|
| `smoke.spec.ts` | Sign-in screen renders (build→serve→browser harness) |
| `foundations.spec.ts` | Fresh account → profile step → lands on the home dashboard (updated 004 — was `/skills`) with a profile row + `(:User)` node (001 quickstart #1 web variant); abandoned profile step re-presented with no profile row written (#5); session survives a reload (#3) |
| `wizard-plan.spec.ts` | Full wizard conversation → goal+plan created atomically in the graph (002 quickstart #1-3); abandoning the wizard mid-conversation leaves no orphaned skill (#4); regenerate too_much→too_easy→cap-at-3, client hides the option past the cap (#5-7); duplicate skill name (any case) shows the warning dialog and "Continue existing" doesn't create a second skill (#8) |
| `voice.spec.ts` | **Run live 2026-07-16, all 6 pass.** Push-to-talk send with `modality: voice` + interim-render timing (US1, SC-004); low-confidence confirm hint + edit-before-send (FR-003 clarified); auto-speak on a real reply + TTS-interrupt timing (US2, SC-004); "Spoken replies" settings toggle persists across reload (US2 scenario 3); permission denial via the web `"not-allowed"` error event shows guidance + disables the mic, chat still works (US3); unsupported-browser simulation proves the same `resolveMicDisabledReason` wiring covers FR-008's browser-support case (US4). Uses `support/voice-mock.ts` — a hand-rolled Web Speech API mock (real STT/TTS accuracy is out of scope; these specs prove the app's *reaction* to recognizer/synthesis events). Found and fixed 5 real bugs getting this suite green — see the git log. |
| `progress-checkins.spec.ts` | **Written 2026-07-17, not yet run live.** Reporting a completed practice in chat records a completed CheckIn against the right step (US1 scenario 1); reporting a struggle records an obstacle CheckIn and the coach responds (US1 scenario 2). Asserts on the resulting graph record, not exact LLM reply text (nondeterministic). |
| `notifications-deep-link.spec.ts` | **Run live 2026-07-18 and reconfirmed 2026-07-25.** `skillcoach://skill/{id}/session` (via `/skill/{id}/session`) lands on that skill's chat (FR-009); an unresolvable id falls back to the dashboard, never a crash; signed-out routes to sign-in (Edge Case). Found+fixed a MAJOR bug 2026-07-18: `usePushNotifications()` called `Notifications.useLastNotificationResponse()` unconditionally, which throws uncaught on web — crashed the **entire web build to a blank page on every route**, undetected until this spec actually ran (no web Playwright spec for any 004-era feature had been executed before that session). Fixed via a `Platform.OS`-based hook-selection pattern. |
| `dashboard.spec.ts` | **Run live 2026-07-18 and reconfirmed 2026-07-25.** Signing in with no skills lands on the dashboard empty state; a wizard-created skill appears as a card (US6); tapping "Mark complete" on a dashboard card records a `source: ui_tap` completed CheckIn and the card updates immediately (US7, SC-007's UI half). Found+fixed 2026-07-18: a `.first()` locator was ambiguous once the shared test account accumulated multiple cards across runs — added this codebase's first `testID` (`dashboard-card-${skill_id}`) to disambiguate. |
| `budget-005.spec.ts` | **Run live 2026-07-25.** Budget-exhausted turn renders as a normal coach bubble in-conversation with localized copy and reset time, chat input stays enabled (mocked API 200 budget turn — doesn't need to actually exhaust the real budget). |
| `onboarding-005.spec.ts` | **Run live 2026-07-25, 3/3.** First-run explainer appears after profile completion, walks both cards, "Enable nudges" completes into the dashboard, never shown again after (direct nav to `/welcome` bounces to dashboard); skipping the explainer also lands on the dashboard and marks it seen; Settings → "Delete account" opens the configured URL in a new tab without navigating away. Caught the two real onboarding-routing bugs described in the automated-index section above. |
| `voice-failures-005.spec.ts` | **Run live 2026-07-25.** V4 offline compose→reconnect→auto-send (real context offline emulation); V1/V3 guidance states render with the chat path still usable (mocked capability probe). |

Support layer: `support/{env,db,auth,network,cleanup,chat,throwaway-user,profile-setup,voice-mock,wizard}.ts`
(`wizard.ts`'s `completeWizard` extracted from `wizard-plan.spec.ts` during 004 so
every later spec needing an existing skill+plan reuses the same scripted flow),
`fixtures/test-users.ts` (PW1/PW2), `support/seed-test-users.ts` (run via `npm run
e2e:seed`; idempotent — creates both accounts and completes their profile step).
`support/db.ts` gained `fetchCheckins` (004); `support/cleanup.ts`'s
`cleanupSkillsByPrefix` now also detach-deletes `CheckIn` nodes — it never did
before 004, which would have orphaned them in Aura on every check-in spec run.

**Not yet automated on web** (see manual checklist): cross-platform simultaneous
sign-in, budget-exceeded UI bubble live render, multi-skill conversation
isolation (already proven at the API layer by `test_skill_isolation.py`), the
004 offline-dashboard-stale-indicator scenario via real network interception
(unit-tested directly against `dashboard-cache.ts` instead, see the jest table).

### Maestro (native) — `app/.maestro/flows/`

| Flow | Covers | Verified on-device? |
|---|---|---|
| `smoke.yaml` | App launches, shows sign-in | Yes (per Phase B tooling commit); reconfirmed manually 2026-08-27 on iOS (physical iPhone 16, personal-team dev build). |
| `session-persists.yaml` | Session survives a full app kill (AsyncStorage — a different code path than the web reload test) | **Yes — 2026-08-27, iOS.** Confirmed manually (sign in, force-kill, relaunch → still signed in) on a physical iPhone 16, personal-team dev build; not yet via a green `maestro test` CLI run — this Intel Mac has no working `idb`/`idb_companion` (Facebook's tap ships an arm64-only bottle, tried and reverted 2026-08-27). |
| `voice-push-to-talk.yaml` | Native push-to-talk hold/speak/release/edit/send (US1) | **Yes — 2026-07-17.** Full end-to-end with real speech ("I want to learn to swim" → edited → sent); the `maestro test` CLI itself is still flaky on this device (gRPC driver timeouts), so this was confirmed by driving the flow directly rather than a green CLI exit. |
| `voice-tts-interrupt.yaml` | Pressing push-to-talk mid-playback stops speech immediately (US2 scenario 2) | **Yes — 2026-07-17.** Coach reply speaking, mic pressed mid-reply, logcat confirmed immediate `Start recognition`; human present confirmed audio stopped instantly. |
| `voice-permission-denied.yaml` | OS permission-dialog denial shows guidance + disables mic, chat still works (US3) | **Yes — 2026-07-17.** Found the flow never actually tested denial (Maestro auto-grants by default); fixed via `launchApp: permissions: microphone: deny`. Real OS dialog denied, guidance shown, chat still worked by text. |
| `voice-failures-005.yaml` | V2 revoke-return where the platform allows, otherwise asserts the recovery screen after a forced error; V6/V7/true-mid-call-focus-loss explicitly deferred to the manual matrix | **No — written, not yet run.** Needs a connected device. |
| `shared/{sign-up,sign-in,complete-profile}.yaml` | Reusable building blocks, not standalone tests | — |

Maestro has no admin-API throwaway-account helper the way Playwright does — flows
assume one pre-existing, already-onboarded account (`.maestro/.env`).

## Manual regression checklist (not yet automated)

### 001 Foundations
1. ~~**iOS sign-up + profile-step flow**~~ — **done, 2026-08-27.** Confirmed live on a physical iPhone 16 (personal-team dev build, see item 23's note below on the entitlements/autolinking fix that made this buildable at all): email sign-up → profile step → Hindi + name + consent → lands in chat. (quickstart #1)
2. **Simultaneous cross-platform identity check** (same account signed in on iOS+Android+web at once) — only partially exercised, not a dedicated concurrent run. (quickstart #4)
3. **Budget-exceeded UI bubble, live on device** — underlying logic covered by `test_budget.py` + contract test 6; the actual rendered bubble wasn't re-verified live (deliberately, to save quota). (quickstart #7)
4. ~~**Native session persistence**~~ — **done, 2026-08-27**, manually on iOS (see Maestro table above; not yet via a green CLI run).

### 002 Wizard & Plan
5. **Multi-skill conversation isolation on a real device** — proven at the API layer (`test_skill_isolation.py`, real bug caught there); not ported to Playwright/Maestro (quickstart #9).
6. **Full scenario walkthrough on a native device** — Playwright covers #1-5, #8 on web; #6/#7 (regenerate variants) are covered indirectly via the combined regenerate spec; native-only rendering (keyboard avoidance, suggested-reply chips) last verified by hand on 2026-07-14 (see quickstart Results).

### 003 Voice Layer
7. **`voice.spec.ts` live run** — **done 2026-07-16**, all 6 scenarios pass live against the deployed stack (see Playwright table above). Found and fixed 5 real bugs in the process (see the git log on `003-voice-layer` for the full list — sttAvailable-on-web, auto-speak-on-stale-message, web permission-denial event, settings-form-remount, plus test-harness fixes).
8. **All three `voice-*.yaml` Maestro flows** — **done, 2026-07-17** (initial attempt 2026-07-16). 2026-07-16 found and fixed a **CRITICAL** real bug: `getSupportedLocales()` is unreliable not just on web (already known) but on **any Android device below API 31** — this was permanently disabling the mic for a supported language on real hardware. Fixed in `voice-capabilities.ts` (see T011 in `specs/003-voice-layer/tasks.md`). 2026-07-17 completed all three flows live with real speech, a real TTS interrupt (human-confirmed), and a real permission-denial dialog — found and fixed two more bugs along the way: Maestro's default permission auto-grant was defeating the denial flow, and a post-sign-in wait condition raced the sign-in screen's own branding text. This device's Maestro *driver* connection remains flaky (gRPC `DEADLINE_EXCEEDED` on long-lived `test` sessions over wireless ADB) — a device/driver characteristic, not an app bug; final confirmation was via direct interaction rather than a clean CLI exit code. See `specs/003-voice-layer/tasks.md` T011/T021/T032 and `quickstart.md`'s Results section for full detail.
9. **`specs/003-voice-layer/quickstart.md`'s 12 scenarios, live** — **done, 2026-07-17.** All 12 confirmed (10 live on-device/browser, 2 via existing targeted automated coverage). See quickstart.md's Results section.
10. ~~**Native permission-prompt string localization, visual check**~~ — **iOS done, 2026-08-27.** Confirmed live on the physical iPhone 16: switching the profile language through EN/HI/ES/FR/DE, the mic-permission OS dialog text was correctly localized each time. Android still unconfirmed.
11. **"Spoken replies" toggle accessibility gap (new)** — the custom Pressable-based switch never sets a DOM `aria-checked` attribute on web (confirmed empirically while debugging `voice.spec.ts`), so screen readers can't announce its state. Not fixed this session — needs either switching to a real ARIA-mapped control or an explicit workaround.

### 004 Progress & Notifications
12. ~~**`progress-checkins.spec.ts`, `notifications-deep-link.spec.ts`, `dashboard.spec.ts` live runs**~~ — **done.** `notifications-deep-link.spec.ts` and `dashboard.spec.ts` both run live and passing (2026-07-18, reconfirmed 2026-07-25). `progress-checkins.spec.ts` ran live 2026-07-18 (bugs found+fixed there too, see git log) but its 2026-07-25 re-run hit the shared test account's exhausted daily LLM budget mid-suite — needs one more clean run after a UTC daily reset to fully close this item, but it is not an open code question.
13. **`specs/004-progress-and-notifications/quickstart.md`'s scenarios, live** — 23/23 scenarios have live or targeted-automated-test evidence recorded in its own Results section (see `specs/004-progress-and-notifications/tasks.md` T069). This checklist item was never updated to reflect that — treat quickstart.md's own Results section as authoritative over this line.
14. **`pg_cron`/`pg_net` actually enabled on this Supabase project's tier** — flagged in research.md R1 as needing live console verification before the nightly cadence scan / session-summarize poll can run for real; still not checked as of 2026-07-25 (same gap 005's own nightly-export workflow needs resolved, see the 005 checklist below).
15. **Live push delivery (device-received Expo push notification)** — **done, 2026-07-18.** Android push confirmed end-to-end on a physical device (Firebase/FCM). iOS push still blocked on the Apple Developer Program enrollment (005 T060).
16. **Maestro `voice-*.yaml` flows re-run against 004's code** — not required by 004 (no native-specific 004 behavior), but worth a sanity pass next time a device session happens, since 004 touched shared navigation (`_layout.tsx`'s redirect target, several screens' back buttons) — 005 touched the same file again (onboarding gate), raising this item's priority slightly for the next device session.
17. **Native permission-prompt localization for `expo-notifications`** — moot: unlike `expo-speech-recognition`, this package has no permission-string plugin config to localize (confirmed via package source, T001/T030) — Android's `POST_NOTIFICATIONS` and iOS's notification prompt both use OS-standard system text, not an app-supplied string.

### 005 Hardening & Pilot
18. **`specs/005-hardening-and-pilot/quickstart.md`'s scenarios, live (T065)** — not yet run as a deliberate walkthrough; blocked on the live migration (next item).
19. **005 Supabase migration never applied to the live project** (`supabase/migrations/20260718000001_hardening_pilot.sql`) — confirmed 2026-07-25 by querying `user_limits`/`model_rates`/`analytics_events` directly (all "table not found"). Supabase's GitHub integration only auto-applies on push to `main`; this feature has been built entirely on its own branch. Blocks live verification of the queue/budget-turn/analytics/ops-views behavior, T033's restore rehearsal, and T049's alert-email validation.
20. **T033 restore rehearsal** (SC-003 requires one before the first pilot invite) — blocked on the migration above plus T032's GitHub repo secrets (nightly-export workflow needs to have produced a real artifact first).
21. **T049 alert-email validation** (deliberate `workflow_dispatch` failure of `spend-check.yml`/`nightly-export.yml`/`healthcheck.yml`) — blocked on T032's repo secrets; `healthcheck.yml` itself needs no secrets and could be validated independently sooner.
22. **Device-only voice-failure matrix cells (V6, V7, true mid-call audio-focus loss)** — explicitly deferred from `voice-failures-005.spec.ts`/`.yaml` to this manual list per T038's own scope note; needs a connected device.
23. **Sign in with Apple, live** — code shipped 2026-07-25 (T054), genuinely untestable until the Apple Developer Program enrollment + Supabase Apple-provider config (T060) exist. **2026-08-27 update — unrelated but relevant fix:** personal Apple dev teams can't provision the Sign In with Apple / Push Notifications capabilities at all (`com.apple.developer.applesignin`, `aps-environment`), which was blocking every iOS build outright. Fixed by excluding `expo-apple-authentication` and `expo-notifications` from iOS autolinking (`package.json`'s `expo.autolinking.ios.exclude`) — durable across `expo prebuild --clean`, verified by regenerating `ios/` from scratch and confirming an empty `SkillCoach.entitlements`. `use-push-notifications.ts` needed an accompanying guarded `require()` (native module now genuinely absent on iOS, and the plain top-level `Notifications.setNotificationHandler(...)` call would otherwise crash the app at launch); `oauth.ts` needed no change (`expo-apple-authentication` already degrades via `requireOptionalNativeModule(...) || {...}`). Confirmed live on iPhone 16, personal-team build: app builds/signs/installs/launches/renders sign-in; the Apple button still renders (iOS-only, unconditional on `Platform.OS`) but tapping it fails soft to the generic auth error toast, no crash; onboarding's push-permission prompt no-ops cleanly with no OS dialog. None of this makes the real features work — that's still T060 plus reverting the exclude.
24. ~~**Native permission-prompt string localization, visual check across all 5 languages**~~ — **iOS done** (item 10 above, 2026-08-27); Android still open.
25. **Restored CI (`ci.yml`, T062) never actually run on GitHub** — the workflow file is written and each job's commands verified locally, but the branch containing it has never successfully pushed (the token used at the time lacked the `workflow` scope) — first real CI run is pending a push.
26. **Voice layer (STT/TTS/push-to-talk/permission-denial) on iOS** — never previously device-tested; every 003 device confirmation (item 8 above) was on Android only. Confirmed working manually 2026-08-27 on the same iPhone 16: push-to-talk hold/record/edit/send, TTS auto-speak with mid-reply interrupt, mic-permission-denial guidance with chat still usable. Item 22's specific V6/V7/audio-focus-loss matrix cells remain unconfirmed on either platform.

## Maintenance

- When a manual item above gets automated, move it out of this checklist and into the matching feature's index table.
- When a new feature lands, add its test files to the index and any leftover manual scenarios to the checklist.
- Cross-check this file is current as part of each feature's quickstart "Exit" section — required by Constitution VIII / Amendment 1.7.0, not optional follow-up.
