# Tasks: Progress Loop & Notifications

**Input**: Design documents from `/specs/004-progress-and-notifications/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: MANDATORY (Constitution VIII — every FR/acceptance scenario/edge
case gets an automated test). Following 002's convention (not 003's
one-off strict-TDD request): write each phase's tests with or before its
implementation tasks, in the order listed. Three categories apply: unit/
contract (pytest), client unit (jest, pure logic), and UX workflow
(Playwright for the Expo web export, Maestro for native — device-
dependent Maestro runs get the same "confirm live, flag if unavailable"
treatment as 001–003).

**Organization**: grouped by user story from spec.md, ordered by priority
tier (P1 stories first, then P2, then P3) rather than spec.md's narrative
order: US1 (P1), US4 (P1), US2 (P2), US3 (P2), US6 (P2), US7 (P2), US5
(P3). Two P1 stories (US1, US4) and four P2 stories (US2, US3, US6, US7)
all build directly on the Foundational phase's CheckIn-write and
progress-read capabilities rather than being fully siloed — see
Dependencies & Execution Order for the real cross-story file touches
(`context_builder.py`, `prompts.py`) this creates.

Revised 2026-07-17 after `/speckit-analyze` (see analysis report): added
T016 (SC-004's simulated multi-week frequency-cap verification, was
uncovered), a rotation-listener bullet + test on T029/T017 (FR-013's
"refreshed when the platform rotates them," was unguarded), a backdated-
timestamp fixture on T004 (Edge Case, was uncovered), T047 (offline-
dashboard stale-data indicator test, was implementation-only), a
notification-copy-localization bullet on T023 (Constitution X, was
unguarded), and fixed T011's NEW → EXTEND (`test_prompts.py` already
exists).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- Paths are repo-relative; structure per plan.md

---

## Phase 1: Setup

- [x] T001 [P] Add `expo-notifications` to `app/package.json`; add its
      config plugin entry (with permission strings) to the `plugins`
      array in `app/app.json`, alongside the existing
      `expo-speech-recognition` entry. **Requires a native rebuild**
      before any push-notification code in this feature can run.
      DONE 2026-07-17: installed via `expo install` (resolved to
      ~57.0.6). No permission-string props exist on this plugin (unlike
      expo-speech-recognition) -- iOS/Android both use the OS's own
      system-provided notification-permission prompt text, and Android's
      POST_NOTIFICATIONS permission is already declared by the package's
      own manifest via autolinking, not a plugin config option. Added the
      plugin entry as a bare string.
- [x] T002 [P] `api/pyproject.toml`: add the `progress_notifications`
      feature marker and six domain markers (`checkins`, `progress`,
      `cadence`, `notifications`, `dashboard`, `sessions`) to the
      `markers` list (Constitution VIII's marker-per-concern convention).

---

## Phase 2: Foundational (blocks all user stories)

**Purpose**: the two capabilities every later story is a thin wrapper
around — writing a `CheckIn` (conversationally or via UI tap) and reading
derived progress from `CheckIn`s (Constitution II) — plus the one shared
constants module (FR-018).

### Tests for Foundational

- [x] T003 [P] pytest EXTEND `api/tests/test_intent_apply.py`: happy-path
      Cypher translation for `log_checkin`, `report_obstacle`,
      `complete_step` (each creates one `CheckIn` with the right
      `outcome`); negative case — a `step_order` not present in the
      skill's active (non-superseded) Plan raises `ValueError` (matches
      the existing `revise_plan`-without-`skill_id` negative-test
      pattern in this file)
      DONE 2026-07-17: the negative case is a pure-Python check in
      `_build` against a new `valid_step_orders: set[int] | None`
      parameter the caller supplies (chat.py/checkins.py both already
      have the skill's plan loaded) — no extra Cypher round-trip, exactly
      mirroring the existing skill_id-missing pattern per the task's own
      hint. 10 new tests added, all passing.
- [x] T004 [P] pytest NEW `api/tests/test_progress.py`: streak/cadence-
      adherence/completed-steps math against hand-computed fixtures
      (SC-002) — include a same-day-duplicate-checkin case (streak counts
      the day once, Edge Case), a broken-then-resumed streak case, a
      per-step behind/not-behind boundary case at exactly
      `constants.CADENCE_BEHIND_MULTIPLIER × expected_interval`, and a
      backdated-`timestamp` case (a `CheckIn` dated 3 days before its
      `created_at` updates streak/cadence-adherence as of `timestamp`,
      not "now" — Edge Case: "I swam twice over the weekend")
      DONE 2026-07-17: 7 tests, all passing.

### Foundational Implementation

- [x] T005 [P] `api/src/skillcoach_api/constants.py` NEW:
      `CADENCE_BEHIND_MULTIPLIER = 1.5`,
      `NOTIFICATION_MAX_PER_SKILL_PER_DAY = 1`,
      `NOTIFICATION_MAX_PER_WEEK = 3`, `QUIET_HOURS_START_HOUR = 8`,
      `QUIET_HOURS_END_HOUR = 20`, `STALE_GOAL_DAYS = 14`,
      `SESSION_INACTIVITY_MINUTES = 30`, `SESSION_SUMMARY_COUNT = 5`
      (research.md R4, FR-018)
- [x] T006 [P] `api/src/skillcoach_api/models/intents.py` EXTEND:
      `LogCheckinIntent` (`step_order`, `outcome: Literal["partial"]`,
      `sentiment`, `obstacle: str | None`), `ReportObstacleIntent`
      (`step_order`, `obstacle: str` required, `sentiment`),
      `CompleteStepIntent` (`step_order`, `sentiment`); `Intent` union
      grows to 7 variants (data-model.md, research.md R5)
      DONE 2026-07-17: also added `timestamp: datetime | None = None` to
      all three (not in research.md R5's field list, but required by
      FR-001 "each check-in captures... timestamp" and the "I swam twice
      over the weekend" backdating edge case — omitted is None, meaning
      "now"). A real gap closed during implementation, same pattern as
      002/003's found-and-fixed planning gaps.
- [x] T007 `api/src/skillcoach_api/services/intent_apply.py` EXTEND:
      `_LOG_CHECKIN`, `_REPORT_OBSTACLE`, `_COMPLETE_STEP` Cypher
      constants — each `MATCH`es the target Step by `(skill_id,
      step_order)` within the active Plan, then `CREATE`s one `CheckIn`
      with `id`, `timestamp`, `outcome`, `sentiment`, `obstacle`, `source`
      — plus `_build` branches for all three (depends on T006; satisfies
      T003)
      DONE 2026-07-17: implemented as ONE shared `_CREATE_CHECKIN`
      constant (research.md R5 itself says "one Cypher shape, three
      outcome values") rather than three textually-identical constants —
      `_CHECKIN_OUTCOME_BY_TYPE` maps intent type -> outcome string.
      `apply_intents` gained `valid_step_orders` and `source` params
      (see T003 note).
- [x] T008 [P] `api/src/skillcoach_api/services/progress.py` NEW:
      `ProgressService` — completed-step set (Steps with ≥1 `CheckIn
      {outcome: "completed"}`), streak (distinct calendar dates in
      `profiles.timezone` with ≥1 `CheckIn`, longest run ending
      today/yesterday), per-step behind-cadence flag (uses
      `constants.CADENCE_BEHIND_MULTIPLIER`) — all read-only, scoped by
      `user_id` (research.md R7; depends on T005; satisfies T004)
      DONE 2026-07-17: `compute(user_id, skill_id, timezone)` takes
      timezone as a parameter (driver-only DI, no MessageStore
      dependency, matching SkillsService's style) — callers fetch it via
      the new `MessageStore.profile_timezone` (mirrors
      `profile_language`). A step with no CheckIn yet uses `Plan.created_at`
      as the behind-cadence anchor (mirrors research.md R9's dashboard
      staleness fallback).
- [x] T009 `api/src/skillcoach_api/services/container.py` EXTEND: wire
      `ProgressService` into the `Services` dataclass (depends on T008)
      DONE 2026-07-17.

**Checkpoint**: the CheckIn write path and the progress read path both
exist and are independently tested — every user story below either
produces CheckIns, reads derived progress, or both.

---

## Phase 3: User Story 1 - Check in on practice (Priority: P1) 🎯 MVP

**Goal**: Conversational check-ins are recorded against the correct step
with outcome/sentiment/obstacle; the coach acknowledges specifically
(celebrates progress, offers a workaround for obstacles); ambiguous
reports get one clarifying question instead of a guess.

**Independent Test**: In a session, report a practice; verify a check-in
is recorded against the correct step with outcome and sentiment, and the
coach acknowledges specifically — no notifications or dashboard needed.

### Tests for User Story 1

- [x] T010 [P] [US1] pytest NEW `api/tests/test_chat_checkins.py`: a
      coaching turn whose `ChatTurn.intents` includes `log_checkin` /
      `report_obstacle` / `complete_step` applies correctly end-to-end
      through `POST /v1/chat` and persists the resulting `CheckIn`
      (contract-level, mirrors `test_chat_wizard.py`'s real-route style)
      DONE 2026-07-17: 4 tests, incl. a step_order-outside-plan negative
      case. Also required extending `routes/chat.py` to compute
      `valid_step_orders` from `context.skill.plan.steps` and thread it
      into `apply_intents`.
- [x] T011 [P] [US1] pytest EXTEND `api/tests/test_prompts.py` case:
      `build_coaching_prompt` documents all three check-in intents (with
      `step_order` grounded in `context.skill.plan.steps`), the
      one-clarifying-question rule for ambiguous reports, and distinct
      guidance per outcome (celebrate completion, acknowledge partial
      progress, offer a concrete workaround for an obstacle)
      DONE 2026-07-17: 4 new tests.
- [x] T012 [P] [US1] Playwright/Maestro: report a practice via chat,
      confirm the coach's reply names the specific step and celebrates;
      separately, report a struggle and confirm the coach offers a
      workaround — extend `app/e2e/playwright/tests/` and add a new
      Maestro flow if the native path needs separate coverage
      DONE 2026-07-17: new `progress-checkins.spec.ts`, 2 scenarios.
      Asserts on the resulting `CheckIn` graph record (source/outcome),
      not exact LLM reply prose (nondeterministic) — same approach as
      wizard-plan.spec.ts's regenerate tests. Extracted `completeWizard`
      out of wizard-plan.spec.ts into a shared `support/wizard.ts` since
      every later 004 spec also needs an existing skill+plan
      precondition. Also fixed a real test-infra leak found in passing:
      `cleanupSkillsByPrefix` detach-deleted Step nodes but never matched
      `CheckIn` nodes attached via `FOR_STEP` — every check-in spec run
      would have orphaned CheckIn nodes in Aura forever. No dedicated
      Maestro flow: the check-in path reuses the same shared
      ConversationView chat UI existing flows already prove works
      natively — no platform-specific behavior here, unlike voice's
      permission APIs. Written but NOT run live this session (needs real
      Supabase/Neo4j/Gemini + spends PW1's LLM budget) — run at the T069
      quickstart exit gate.

### Implementation for User Story 1

- [x] T013 [US1] `api/src/skillcoach_api/services/prompts.py` EXTEND
      `build_coaching_prompt`: teach the LLM `log_checkin`,
      `report_obstacle`, `complete_step` (when to emit each, referencing
      `step_order` from the plan already in context), the ambiguous-
      report clarifying-question rule, and per-outcome tone (depends on
      T007; satisfies T010, T011)
      DONE 2026-07-17.

**Checkpoint**: US1 fully functional and independently testable — check-
ins recorded correctly from ordinary conversation.

---

## Phase 4: User Story 4 - Nudge when behind cadence (Priority: P1)

**Goal**: A nightly scan finds users behind their plan's cadence (no
check-in within `constants.CADENCE_BEHIND_MULTIPLIER` × the expected
interval), sends exactly one push per skill per day within the frequency
cap and quiet hours, and the deep link opens straight into that skill's
session with the coach already aware of the gap.

**Independent Test**: Set up a plan with a known cadence, record no
check-ins past the threshold, verify exactly one reminder arrives, and
confirm tapping it opens the right skill with a gap-aware opening
message.

### Tests for User Story 4

- [x] T014 [P] [US4] pytest NEW `api/tests/test_cadence_schedule.py`:
      `sync()` writes one row per step on `create_plan`/`revise_plan`; a
      later `revise_plan` replaces rows for step orders that no longer
      exist in the new plan
      DONE 2026-07-17: implemented as delete-all-then-insert-current
      (trivially satisfies "replace" with no row-by-row diffing needed).
      4 tests incl. `all_rows()` (the scan's fan-out read).
- [x] T015 [P] [US4] pytest NEW `api/tests/test_notifications.py`:
      frequency cap (max 1/skill/day, max 3/week, from `notifications`
      table history) enforced; quiet-hours window respected against
      `profiles.timezone`; OS-permission-denied / no-active-token case
      skips silently with no error (User Story 4 scenario 4); 3+ skills
      behind at once → one notification per skill, never a burst (Edge
      Case)
      DONE 2026-07-17: 20 tests (push tokens, is_daytime incl. real-
      timezone-not-UTC case, both frequency windows, send_cadence_nudge's
      full outcome matrix, the 3-skills-at-once Edge Case, a 4th-skill-
      hits-weekly-cap case).
- [x] T016 [P] [US4] pytest NEW `api/tests/test_notifications.py` case:
      simulate `notifications/scan` running once daily across a
      synthetic multi-week fixture (mixed on-cadence / behind-cadence
      users) — assert zero notifications for on-cadence users throughout,
      and the frequency cap (1/skill/day, 3/week) is never exceeded for
      behind-cadence ones across the whole simulated run (SC-004's
      "verified over a simulated multi-week run," distinct from T015's
      single-instant boundary checks)
      DONE 2026-07-17: two tests — a 21-day (3-week) simulation against
      `NotificationsService.send_cadence_nudge` directly (injectable
      `now`, real FakeRest state carried across all 21 calls) proving
      both windows' caps hold throughout; a separate real-route test
      proving an on-cadence skill never even reaches
      `send_cadence_nudge` (that boundary lives in routes/internal.py,
      not the service).
- [x] T017 [P] [US4] pytest NEW `api/tests/test_notifications_contract.py`:
      `POST`/`DELETE /v1/push-tokens` (upsert-on-conflict register,
      idempotent revoke, and a re-registration case simulating a
      platform-rotated token replacing the prior one — FR-013); `POST
      /v1/internal/notifications/scan` returns 401 (standard error
      envelope) without the correct `X-Internal-Secret` header
      DONE 2026-07-17: 8 tests.
- [x] T018 [P] [US4] pytest EXTEND `api/tests/test_context_builder.py`:
      when a skill has a behind-cadence step, `build()`'s
      `ConversationContext` includes a gap description (which step, how
      long); when nothing is behind, no gap description is present
      DONE 2026-07-17: added `FakeProgress`, 2 new tests + updated all
      existing ones for the new constructor arg.
- [x] T019 [P] [US4] Maestro/Playwright: simulate tapping a
      `skillcoach://skill/{id}/session` deep link — verify it opens
      directly on that skill's session; signed-out or unresolvable-skill
      case routes to sign-in / a safe fallback, never a crash (Edge Case)
      — new `app/.maestro/flows/`, extend Playwright where testable on
      web
      DONE 2026-07-18: `notifications-deep-link.spec.ts` was written
      during the original implementation but never actually run until
      today. Running it for the first time found a MAJOR, previously
      undiscovered bug: `usePushNotifications()` (called unconditionally
      from the root layout) calls `Notifications.useLastNotificationResponse()`,
      which throws a fatal, uncaught error on web -- crashing the ENTIRE
      web build to a blank page on every single route, not just this
      one. Fixed by selecting a no-op implementation on web at module
      scope (Platform.OS is fixed for the app's lifetime, so this never
      violates React's rules of hooks) instead of patching the one
      throwing call, since the rest of that surface isn't fully
      supported on web either (expo-notifications itself warns
      `addPushTokenListener` is a no-op there). All 3 scenarios in the
      spec now pass live (normal deep-link routing, unresolvable-skill
      fallback, signed-out fallback) -- confirmed both in isolation and
      as part of a full suite run. The real native-tap half (beyond
      "simulate") was ALSO verified this session, live, on a physical
      device with a real push notification -- see quickstart.md's
      Results section, scenario 10. No Maestro flow was written
      (Playwright covers the web-testable routing contract, and the
      live device test exceeds what a Maestro simulation would prove).
      Running the full suite once this crash was fixed also surfaced
      (and got fixed) 2 more real, previously-hidden bugs: a BigInt
      arithmetic error in progress-checkins.spec.ts (neon4j-driver v6
      returns Cypher integers as native BigInt, not number -- `Math.min`
      can't spread them) and a genuine test-scoping bug in
      dashboard.spec.ts (`.first()` on generic "Mark complete" text is
      ambiguous once the shared PW1 account has multiple skill cards --
      added a minimal `testID` to the dashboard card, the first testID
      in this codebase, specifically because no text-based locator can
      disambiguate two structurally-identical repeated cards). Both
      fixes are in and type/lint-clean, but re-verifying them live is
      blocked until tomorrow: PW1 hit 89/50 of its daily LLM budget and
      PW2 45/50 from this session's own repeated wizard-heavy test runs
      (confirmed via `llm_usage`, not a mystery) -- 2 more Playwright
      failures on this run (`voice.spec.ts`, unrelated to any of this
      session's changes) are the same budget exhaustion, not new
      regressions.

### Implementation for User Story 4

- [x] T020 [US4] Migration NEW `supabase/migrations/2026071X_progress_notifications.sql`:
      `cadence_schedules`, `push_tokens`, `notifications` tables
      (data-model.md)
      DONE 2026-07-17 as `20260717000001_progress_notifications.sql`.
- [x] T021 [P] [US4] `api/src/skillcoach_api/services/cadence_schedule.py`
      NEW: `CadenceScheduleService.sync(user_id, skill_id, steps)` —
      upsert one row per step, replace-on-revise (depends on T020;
      satisfies T014)
      DONE 2026-07-17: plus `all_rows()` for the scan's fan-out.
- [x] T022 [US4] `api/src/skillcoach_api/routes/chat.py` EXTEND: after
      `apply_intents` succeeds, if the batch contained `create_plan` or
      `revise_plan`, call `CadenceScheduleService.sync(...)` (depends on
      T021)
      DONE 2026-07-17. Also extended `routes/skills.py`'s regenerate
      endpoint the same way (a real gap: regenerate emits `revise_plan`
      too, and FR-008 must hold regardless of which endpoint revised the
      plan) — found + fixed a genuine bug while doing so: naively reusing
      the pre-similarity-retry `new_steps` variable there would have
      synced the DISCARDED near-duplicate first attempt's steps, not
      the one actually applied. Fixed + regression-tested.
- [x] T023 [P] [US4] `api/src/skillcoach_api/services/notifications.py`
      NEW: `NotificationsService` — push-token upsert/revoke (Postgres),
      Expo push send via `httpx` (research.md R3), frequency-cap +
      quiet-hours check against `notifications` history +
      `profiles.timezone`, delivery-outcome logging — notification
      body/title text is selected per-recipient from a small server-side
      i18n table keyed by `profiles.language`, never hard-coded English
      (Constitution X) (depends on T005, T020; satisfies T015, T016)
      DONE 2026-07-17. Quiet-hours/frequency-cap skips log nothing (the
      `notifications` check constraint has no status value for "never
      attempted" — those are pre-send scheduling gates, not delivery
      outcomes); `SupabaseRest` gained `update()`/`delete()` and
      `select_many`'s `raw_filters` to support this (with their own
      tests).
- [x] T024 [US4] `api/src/skillcoach_api/routes/notifications.py` NEW:
      `POST`/`DELETE /v1/push-tokens` (auth'd via `RequirePrincipal`,
      scoped to the caller) (depends on T023; partially satisfies T017)
      DONE 2026-07-17.
- [x] T025 [US4] `api/src/skillcoach_api/config.py` EXTEND:
      `Settings.internal_secret: str = ""`; new
      `api/src/skillcoach_api/internal_auth.py`: a dependency checking
      `X-Internal-Secret` against it, mirroring `RequirePrincipal`'s
      shape but for system-to-system calls (research.md R1)
      DONE 2026-07-17: fails closed when unconfigured (empty secret never
      matches, including another empty header).
- [x] T026 [US4] `api/src/skillcoach_api/routes/internal.py` NEW:
      `POST /v1/internal/notifications/scan` — reads `cadence_schedules`,
      checks each candidate step's recency via `ProgressService`'s
      behind-cadence helper, applies the frequency cap/quiet hours via
      `NotificationsService`, sends and logs, returns scan summary counts
      (depends on T008, T021, T023, T025; satisfies remainder of T017)
      DONE 2026-07-17. `StepProgress` gained an internal-only `anchor_at`
      field (last_checkin_at, or Plan.created_at when never checked in)
      so "days since" is computable even for a step with zero check-ins
      — not part of the public progress/dashboard API shape (T033).
- [x] T027 [US4] `api/src/skillcoach_api/services/context_builder.py`
      EXTEND: `build()` computes a gap description when any step is
      behind cadence, using `ProgressService` (depends on T008; satisfies
      T018)
      DONE 2026-07-17: `ContextBuilder` gained a `ProgressService`
      dependency (wired in container.py); `ConversationContext.
      gap_description` defaults to `None` so existing direct-construction
      call sites (routes/skills.py's regenerate) are unaffected.
- [x] T028 [US4] `api/src/skillcoach_api/services/prompts.py` EXTEND
      `build_coaching_prompt`: when context carries a gap description,
      open by naming the specific missed step/elapsed time, supportively
      not punitively (SC-001) (depends on T013, T027)
      DONE 2026-07-17.
- [x] T029 [P] [US4] `app/src/hooks/use-push-notifications.ts` NEW:
      requests permission + registers the Expo push token on sign-in,
      `POST`s to `/v1/push-tokens`, `DELETE`s on sign-out, routes a
      notification tap to the deep-linked skill's session — also
      subscribes to `Notifications.addPushTokenListener` and re-`POST`s
      `/v1/push-tokens` on rotation while the app is already
      foregrounded, not just at sign-in (FR-013's "refreshed when the
      platform rotates them," satisfies remainder of T017)
      DONE 2026-07-17: also handles the cold-start case (app launched by
      tapping a notification) via `Notifications.useLastNotificationResponse`.
      Pure helpers (`resolvePushPlatform`, `extractSkillIdFromNotificationData`)
      live in a new `lib/push-notifications.ts` rather than the hook file
      itself — the hook transitively imports `lib/api.ts` → `lib/
      supabase.ts` → AsyncStorage, which isn't mocked in this project's
      jest setup and made the pure functions untestable in-file; 6 jest
      tests. `getExpoPushTokenAsync()` fails soft (caught, logged, no
      token registered) if it ever throws — flagged 2026-07-17 when no
      EAS project existed yet (needed purely for Expo's push-token
      *service* identity, unrelated to EAS Build/CI, which this app still
      doesn't use); **resolved 2026-07-18** — an EAS project
      linked, `extra.eas.projectId` set in
      `app.json`. The already-flagged Apple Developer Program (iOS push
      entitlement) and Firebase (Android FCM credentials) items in
      docs/getting-started.md still block live push delivery. `api.ts`
      gained `postPushToken`/`deletePushToken` plus a `requestVoid` helper
      (204 No Content responses can't go through `request<T>`, which
      always calls `.json()` on success).
- [x] T030 [P] [US4] `app/app.json` EXTEND: `expo-notifications` plugin
      config + permission strings across all 5 launch languages (depends
      on T001)
      DONE 2026-07-17 (already covered by T001) — no further action:
      `expo-notifications`' plugin has no permission-string config option
      at all (unlike `expo-speech-recognition`'s microphone/speech-
      recognition strings), and Android's `POST_NOTIFICATIONS` permission
      is declared by the package's own manifest via autolinking, not a
      plugin option. Nothing to translate for this specific permission.
- [x] T031 [US4] Deep-link handling: `skillcoach://skill/{id}/session`
      resolves via `expo-router` to `chat.tsx` for that `skill_id`;
      signed-out/unresolvable-skill falls back safely (Edge Case)
      (depends on T029; satisfies T019)
      DONE 2026-07-17: new `app/(main)/skill/[id]/session.tsx` --
      expo-router's file-based routing resolves the reserved
      `skillcoach://` scheme automatically; this route just redirects
      into `/chat?skillId=X`. Signed-out already falls back to sign-in
      for free via the existing root auth gate (any screen, not
      deep-link-specific). New `notifications-deep-link.spec.ts` (3
      Playwright scenarios: happy path, unresolvable id, signed-out) --
      written, not run live this session (same T069 deferral as T012).
      No Maestro flow: nothing here is native-platform-specific --
      expo-router's scheme handling and the redirect component are pure
      JS, already exercised identically by the Playwright coverage.

**Checkpoint**: US1 + US4 both work independently — the full nudge → tap
→ gap-aware-session loop is functional (SC-001).

---

## Phase 5: User Story 2 - See progress at a glance (Priority: P2)

**Goal**: Each skill has a progress view (completed steps, streak,
cadence adherence) computed from `CheckIn`s, agreeing regardless of
platform or when it's viewed.

**Independent Test**: Record a known sequence of check-ins, open the
progress view, and verify streaks, completed steps, and cadence adherence
match hand-computed values.

### Tests for User Story 2

- [x] T032 [P] [US2] pytest NEW `api/tests/test_progress_contract.py`:
      `GET /v1/skills/{id}/progress` shape and values match
      `ProgressService` output for a fixture check-in sequence; two
      requests in a row return identical values (no drift, FR-004)
      DONE 2026-07-17: 5 tests (shape/values, drift-free repeat call,
      user-scoping, 404 for missing/not-owned, auth-required). Passed on
      the first run.

### Implementation for User Story 2

- [x] T033 [P] [US2] `api/src/skillcoach_api/models/progress.py` NEW:
      response models for `GET /v1/skills/{id}/progress` (shared shape
      also used by the dashboard, Phase 7)
      DONE 2026-07-17: `SkillProgressResponse.from_domain()` maps from
      `ProgressService`'s dataclasses rather than reusing them directly,
      so internal-only fields (`StepProgress.anchor_at`, added in Phase
      4) never leak into the public shape — verified by a test asserting
      `anchor_at` absent from the response body.
- [x] T034 [US2] `api/src/skillcoach_api/routes/progress.py` NEW:
      `GET /v1/skills/{id}/progress` (depends on T008, T033; satisfies
      T032)
      DONE 2026-07-17.
- [x] T035 [US2] `app/src/app/(main)/skill/[id]/progress.tsx` NEW:
      renders completed steps, streak, and per-step cadence adherence
      DONE 2026-07-17: reachable via a new "View progress" link on
      plan-review.tsx (previously nothing linked to this screen). Adds
      `progress.*` i18n keys across all 5 launch languages.
- [x] T036 [P] [US2] `app/src/lib/api.ts` EXTEND: `fetchSkillProgress`
      call
      DONE 2026-07-17: named `getSkillProgress` to match this file's
      existing `getSkill`/`getSkills` convention rather than the task's
      `fetch*` naming.

**Checkpoint**: US1, US4, US2 all independently functional.

---

## Phase 6: User Story 3 - The coach remembers (Priority: P2)

**Goal**: Session end (including abandoned conversations) triggers a
stored summary; new sessions include the last N summaries in the coach's
context.

**Independent Test**: Hold a session with distinctive content, end it,
start a new session, and verify the coach's opening reflects the prior
session's summary.

### Tests for User Story 3

- [x] T037 [P] [US3] pytest NEW `api/tests/test_session_summary.py`:
      inactivity-boundary detection (a session is eligible only once its
      last message is older than `constants.SESSION_INACTIVITY_MINUTES`
      with no `Session` node yet); a `skill_id IS NULL` session (wizard)
      is never summarized; a summarization failure is logged and does not
      block the next session from starting (FR-006 scenario 3)
      DONE 2026-07-17: the eligibility filter (inactivity cutoff,
      `skill_id IS NULL` exclusion) lives in the SQL RPC
      (`eligible_sessions_for_summary`, new migration function), same
      Postgres-fan-out/Neo4j-decision split as the notifications scan —
      so this file proves the service's contract with that RPC (cutoff
      passed, what it does with candidates) rather than the SQL itself,
      same division of labor as `test_notifications.py`. 5 tests incl.
      failure-isolation (session-1's LLM call fails, session-2 still
      succeeds).
- [x] T038 [P] [US3] pytest EXTEND `api/tests/test_context_builder.py`:
      `build()` includes the last `constants.SESSION_SUMMARY_COUNT`
      `Session` summaries for that skill, most-recent-relevant ordering
      DONE 2026-07-17: 2 new tests + `FakeSkills` gained
      `recent_session_summaries`.
- [x] T039 [P] [US3] pytest EXTEND `api/tests/test_notifications_contract.py`:
      `POST /v1/internal/sessions/summarize` also rejects a missing/wrong
      `X-Internal-Secret` (same auth helper as T017)
      DONE 2026-07-17: 3 tests (missing, wrong, correct secret).

### Implementation for User Story 3

- [x] T040 [P] [US3] `api/src/skillcoach_api/models/session_summary.py`
      NEW: internal-only `SessionSummary` model (bounded length) — never
      part of the `Intent` union (research.md R5)
      DONE 2026-07-17: `max_length=800`.
- [x] T041 [US3] `api/src/skillcoach_api/services/session_summary.py`
      NEW: finds eligible `(skill_id, session_id)` pairs from `messages`
      past the inactivity timeout with no `Session` node yet, summarizes
      via the cheap LLM tier (budgeted per FR-012), writes
      `(:Skill)-[:HAS_SESSION]->(:Session)` (depends on T005, T040)
      DONE 2026-07-17: new migration function `eligible_sessions_for_
      summary(cutoff)` (PostgREST has no GROUP BY/HAVING) does the
      Postgres-side fan-out; the service checks each candidate against
      Neo4j for an existing Session node, then summarizes+writes.
      "Cheap LLM tier" = the same already-configured model/runnable —
      this app has no second tier active yet (Constitution VI's
      provider/tier switch is deferred to feature 005) — reusing
      `LlmService`'s existing `ChatTurn`-schema call rather than
      provisioning a separate structured-output type just for this one
      internal call; only `.reply` is used, intents ignored.
- [x] T042 [US3] `api/src/skillcoach_api/routes/internal.py` EXTEND:
      `POST /v1/internal/sessions/summarize` (depends on T025, T041;
      satisfies T039)
      DONE 2026-07-17.
- [x] T043 [US3] `api/src/skillcoach_api/services/context_builder.py`
      EXTEND: `build()` fetches the last N `Session` summaries for the
      skill (depends on T005; satisfies T038) — sequential after T027,
      same file
      DONE 2026-07-17: new `SkillsService.recent_session_summaries`
      (most-recent-first via `ORDER BY sess.ended_at DESC`).
- [x] T044 [US3] `api/src/skillcoach_api/services/prompts.py` EXTEND
      `build_coaching_prompt`: weave recent-session-summary context into
      the opening naturally, e.g. "Last time X was frustrating — how did
      this week go?" (SC-003) (depends on T028, T043)
      DONE 2026-07-17.
- [x] T045 [US3] `api/src/skillcoach_api/services/container.py` EXTEND:
      wire `SessionSummaryService`
      DONE 2026-07-17.

**Checkpoint**: US1, US4, US2, US3 all independently functional —
continuity works across sessions.

---

## Phase 7: User Story 6 - See all pursuits at a glance (Priority: P2)

**Goal**: Signing in lands the user on a home dashboard — every skill as
a card (goal + plan + derived progress), stale goals visibly marked with
continue/revise-in-conversation/start-new (never delete), an empty state
for zero skills.

**Independent Test**: With two or more skills in different states (one on
cadence, one stale), open the app and verify both render as cards with
accurate goal/plan/progress information, matching each skill's own
progress view.

### Tests for User Story 6

- [x] T046 [P] [US6] pytest NEW: `GET /v1/dashboard` shape, per-skill
      staleness flag, agreement with `GET /v1/skills/{id}/progress`
      (SC-006), zero-skills empty response (FR-014 scenario 2), and a
      staleness boundary case at exactly `constants.STALE_GOAL_DAYS` —
      extend `api/tests/test_progress_contract.py`
      DONE 2026-07-17: 5 tests. `FakeProgress` extended to accept a
      `dict[skill_id, SkillProgress]` for multi-skill dashboard scenarios.
- [x] T047 [P] [US6] jest/Playwright: simulate a failed `GET
      /v1/dashboard` refetch while a prior successful response is
      cached; assert the cached dashboard renders with a stale-data
      indicator (quickstart scenario 22, research.md R10) — new
      `app/src/lib/dashboard-cache.test.ts` and/or extend
      `app/e2e/playwright/tests/`
      DONE 2026-07-17: `dashboard-cache.test.ts` (3 tests) covers the
      caching module directly -- AsyncStorage's native module isn't
      available under plain jest-expo, so this file scopes the library's
      own official jest mock to itself via `jest.mock(...)`, no shared
      config change. New `dashboard.spec.ts` Playwright spec (2
      scenarios: redirect + wizard-created skill appears as a card) --
      written, not run live yet (same T069 deferral as other 004
      Playwright specs). Also fixed a real regression this phase's
      redirect change caused: `foundations.spec.ts`'s post-profile
      landing assertion still expected `**/skills`.
- [x] T048 [US6] `api/src/skillcoach_api/routes/progress.py` EXTEND:
      `GET /v1/dashboard` — composes `SkillsService.list_skills` +
      `ProgressService` per skill + staleness check
      (`constants.STALE_GOAL_DAYS` against the most recent `CheckIn`, or
      `Skill.created_at` if none) (depends on T008, T033; satisfies T046)
      DONE 2026-07-17.
- [x] T049 [US6] `app/src/app/(main)/dashboard.tsx` NEW: home dashboard —
      one card per skill (goal/plan/progress), stale marking with
      continue / revise-in-conversation / start-new (never delete,
      FR-017), empty state guiding to the feature 002 wizard
      DONE 2026-07-17: extracted the duplicate-skill-name check
      (normalize/levenshtein/findDuplicate) out of skills.tsx into a
      shared `lib/duplicate-skill.ts` so both screens use the identical
      Add-skill flow rather than duplicating it. `skills.tsx` itself is
      kept (not deleted) -- same precedent as 001's /chat staying
      reachable after 002 made /skills the landing screen.
- [x] T050 [US6] `app/src/app/index.tsx` EXTEND: redirect target changes
      from `/skills` to `/dashboard` (depends on T049)
      DONE 2026-07-17: also updated `_layout.tsx`'s post-auth-gate
      redirect (the one that actually fires after sign-in/profile
      completion -- index.tsx's own redirect is superseded by it before
      profile exists) and every "back to home" arrow across chat.tsx/
      plan-review.tsx/progress.tsx/session.tsx's deep-link fallback that
      previously pointed at `/skills`.
- [x] T051 [P] [US6] `app/src/lib/dashboard-cache.ts` NEW: `AsyncStorage`
      read/write for the offline stale-data indicator (research.md R10;
      satisfies T047)
      DONE 2026-07-17.
- [x] T052 [P] [US6] `app/src/lib/api.ts` EXTEND: `fetchDashboard` call
      DONE 2026-07-17: named `getDashboard` (matches `getSkills`/
      `getSkillProgress` convention, same naming deviation as T036).

**Checkpoint**: US1, US4, US2, US3, US6 all independently functional —
the dashboard is the new landing surface.

---

## Phase 8: User Story 7 - Mark a step done without a conversation (Priority: P2)

**Goal**: A plan step is completable (full or partial) via a UI tap on
the dashboard, bypassing the LLM entirely, validated and applied through
the identical pipeline as a conversational intent.

**Independent Test**: Tap a step to mark it complete; verify a `CheckIn`
record is created with `source: ui_tap`, no LLM call is made, and the
dashboard/progress view update immediately.

### Tests for User Story 7

- [x] T053 [P] [US7] pytest NEW `api/tests/test_checkins_contract.py`:
      `POST /v1/intents/apply` happy path for `complete_step` and
      `log_checkin`; `source` is always `ui_tap` regardless of request
      body (FR-016); a validation failure surfaces the error directly
      with no retry (FR-015); zero LLM calls asserted (no `LlmService`
      invocation, SC-007)
      DONE 2026-07-17: 10 tests. SC-007's zero-LLM-call guarantee is
      proven by wiring the fake `services` container with NO `llm`/
      `budget` attribute at all — an accidental call anywhere on this
      path would `AttributeError` immediately rather than silently
      succeed against an unused fake. `ApplyResult` gained a `checkin_id`
      field (the route's response needs it; `apply_intents` now tracks
      the last check-in intent's generated id the same way it already
      tracked `created_skill_id`).
- [x] T054 [P] [US7] Maestro/Playwright: tap "mark complete" on a
      dashboard card, verify dashboard + progress view update
      immediately; tap "log partial progress," verify the step stays
      open; double-tap in quick succession produces no double-crediting
      (Edge Case)
      DONE 2026-07-17: new Playwright scenario in `dashboard.spec.ts`
      (wizard-created skill → tap "Mark complete" → real CheckIn with
      `source: ui_tap` → card re-renders with the updated count) —
      written, not run live yet (T069 deferral). Double-tap/log-partial
      coverage lives at the API contract level in
      `test_checkins_contract.py` (double-tap produces two independent,
      correctly-recorded CheckIns per data-model.md's append-only design
      — not deduped, matching the same-day-duplicate Edge Case already
      proven not to double-count at the streak layer in
      `test_progress.py`); no separate Maestro flow — nothing here is
      native-platform-specific.
- [x] T055 [P] [US7] `api/src/skillcoach_api/models/checkins.py` NEW:
      `UiIntent` union (`CompleteStepIntent | LogCheckinIntent` only, not
      `ReportObstacleIntent` — research.md R6) + request/response models
      for `POST /v1/intents/apply`
      DONE 2026-07-17.
- [x] T056 [US7] `api/src/skillcoach_api/routes/checkins.py` NEW:
      `POST /v1/intents/apply` — validates `UiIntent`, forces
      `source="ui_tap"` server-side, calls
      `IntentApplyService.apply_intents` directly with no LLM/budget call
      (depends on T007, T055; satisfies T053)
      DONE 2026-07-17.
- [x] T057 [US7] `app/src/app/(main)/dashboard.tsx` EXTEND: tap-to-
      complete / log-partial affordance per step on each card (depends on
      T049)
      DONE 2026-07-17: required extending `GET /v1/dashboard`'s response
      with a per-step list (`steps: [{order, description, completed,
      behind_cadence}]`, new `DashboardStepCard` model) — the original
      aggregate-only shape (Phase 7) had no way to identify individual
      steps to tap. `contracts/api.md` updated to reflect this. Also
      made the dashboard route's per-step progress lookup defensive
      (`.get()` not `[]`) against the two reads (`get_skill`, `progress.
      compute`) racing a concurrent `revise_plan`.
- [x] T058 [P] [US7] `app/src/lib/api.ts` EXTEND: `postIntentApply` call
      DONE 2026-07-17.

**Checkpoint**: US1, US4, US2, US3, US6, US7 all independently
functional.

---

## Phase 9: User Story 5 - Adjust the goal (Priority: P3)

**Goal**: A conversational goal revision creates a superseding goal
preserving history; a plan regenerated afterward links to the new goal;
future coaching reflects and can reference the trajectory.

**Independent Test**: Revise a goal in conversation; verify a new goal
supersedes the old, the old remains in history, and the coach subsequently
coaches to the new goal.

`revise_goal` (`ReviseGoalIntent`) already exists and is already wired
into `build_coaching_prompt` from feature 002 — this phase closes two
real gaps found during 004's planning research, not a from-scratch build:

1. `_REVISE_PLAN`'s Cypher currently links a regenerated plan to whatever
   Goal the *previous* plan pointed to, not the skill's *current* active
   goal — so a plan regenerated after a goal revision would silently keep
   pointing at the superseded goal (violates FR-011's explicit
   requirement).
2. The coach has no way to reference the goal's trajectory today —
   `build_coaching_prompt` only sees the current goal, never superseded
   ones.

### Tests for User Story 5

- [x] T059 [P] [US5] pytest EXTEND `api/tests/test_intent_apply.py`:
      `revise_plan` issued after a prior `revise_goal` links the new
      `Plan`'s `FOR_GOAL` to the currently-active (non-superseded) `Goal`,
      not the old plan's goal — regression test for the gap above
      DONE 2026-07-17: asserts the fixed query text directly (the
      `FakeDriver` captures Cypher text, not simulated cross-call graph
      state, so this proves the query shape changed, matching this
      file's existing style for similar regressions).
- [x] T060 [P] [US5] pytest EXTEND `api/tests/test_skills_service.py` (or
      `test_context_builder.py`): skill detail / context includes goal
      revision history (prior statements + target dates) when superseding
      goals exist
      DONE 2026-07-17: 3 tests in `test_skills_service.py` for the new
      `SkillsService.goal_revision_history` method.
- [x] T061 [P] [US5] pytest EXTEND `api/tests/test_context_builder.py`:
      after two goal revisions, all three goals are retrievable in order
      (SC-005)
      DONE 2026-07-17: 2 tests.

### Implementation for User Story 5

- [x] T062 [US5] `api/src/skillcoach_api/services/intent_apply.py` FIX:
      `_REVISE_PLAN` looks up the skill's current active `Goal` directly
      (`MATCH (s)-[:HAS_GOAL]->(g:Goal) WHERE NOT
      (g)<-[:SUPERSEDES]-(:Goal)`) instead of following the old `Plan`'s
      existing `FOR_GOAL` edge (depends on T007; satisfies T059)
      DONE 2026-07-17.
- [x] T063 [US5] `api/src/skillcoach_api/services/skills.py` EXTEND:
      expose goal revision history (the `SUPERSEDES` chain) for context-
      building purposes
      DONE 2026-07-17: `goal_revision_history` walks forward from the
      active Goal through zero or more `SUPERSEDES` edges in one query,
      returning oldest-first (current goal always last).
- [x] T064 [US5] `api/src/skillcoach_api/services/context_builder.py`
      EXTEND: `build()` includes goal revision history when superseded
      goals exist (depends on T063; satisfies T060, T061)
      DONE 2026-07-17: `ConversationContext.goal_history` always
      populated when a skill is active (even with just the current
      goal) — `build_coaching_prompt` (T065) is the layer that decides
      whether there's anything worth referencing.
- [x] T065 [US5] `api/src/skillcoach_api/services/prompts.py` EXTEND
      `build_coaching_prompt`: reference the goal's trajectory when
      history exists (e.g. "you originally aimed for October") (depends
      on T044, T064)
      DONE 2026-07-17: only emits the trajectory note when
      `goal_history` has more than one entry (a single entry means no
      revisions -- nothing to reference beyond the current goal already
      shown elsewhere in the prompt).

**Checkpoint**: all seven user stories independently functional.

---

## Phase 10: Polish & Cross-Cutting

- [x] T066 [P] `docs/testing.md`: add a "Feature 004 — Progress &
      Notifications" section (automated test index table, manual
      regression checklist entries for device-dependent Maestro flows and
      live push-delivery/cron scenarios)
      DONE 2026-07-17: full test index (8 new files + extensions to 8
      existing ones), jest table extended, 3 new Playwright specs
      documented (not yet run live), manual checklist items 12-17 added
      for what's still outstanding (live spec runs, quickstart, `pg_cron`/
      `pg_net` console check, live push delivery blocked on the Apple/
      Firebase gaps — the EAS-project gap was resolved 2026-07-18). Also
      fixed a stale line: `foundations.spec.ts`'s description still said
      "lands on /skills" after Phase 7's redirect change.
- [x] T067 [P] Document the new endpoints, `constants.py`, and the two
      internal cron endpoints' `pg_cron`/`pg_net` wiring (wherever 001–003
      documented equivalent additions)
      DONE 2026-07-17: `api/README.md` gained the 8 new endpoint rows,
      a `constants.py` rationale note, an "Internal cron endpoints"
      section explaining the shared-secret auth + where the `pg_cron`/
      `pg_net` wiring actually lives (Supabase console, not this repo's
      migrations), the `progress_notifications` marker in the test-suite
      section, and a note on the new migration's `eligible_sessions_for_
      summary` SQL function.
- [x] T068 Run the full `pytest` and `jest` suites; confirm green,
      including the new `progress_notifications` marker
      DONE 2026-07-17: 305/305 pytest (122 collected under `-m
      progress_notifications`), 34/34 jest, tsc/eslint clean on the app,
      ruff clean on the api (2 pre-existing, unrelated formatting
      findings in files 004 never touched).
- [◐] T069 Run all 23 `quickstart.md` scenarios live (feature exit gate,
      Constitution VIII; SC-001–SC-007) — record a Results section in
      quickstart.md, including live verification that `pg_cron`/`pg_net`
      are actually enabled on this Supabase project's tier (research.md
      R1)
      PARTIAL 2026-07-18: ran live against a physical Android device +
      the real Supabase/Neo4j/Gemini stack. Found two blocking bugs
      before the suite could finish — full Results section in
      quickstart.md:
      (1) the 004 migration (`cadence_schedules`/`push_tokens`/
      `notifications`/`eligible_sessions_for_summary`) was never applied
      to the live Supabase project, which 500s every chat-driven plan
      create/revise, all of US3's session summaries, and all of US4's
      notifications;
      (2) `routes/chat.py` applies intents (committing to Neo4j) BEFORE
      the separately-failable `cadence_schedule.sync()` call, so that
      failure reports "something went wrong" while the skill/goal/plan
      was already persisted — a real phantom-success bug, not just a
      symptom of (1). 14 of 23 scenarios passed live (1,2,3,5,6,14,16,
      18-23) plus a Hindi dashboard spot-check; scenario 4 (ambiguous
      report) deviated from spec (coach guessed instead of asking);
      7-13 blocked by (1); 15 (multi-skill)/17 (stale goal) not reached;
      ES/FR/DE smoke pass not done. `pg_cron`/`pg_net` still unverified
      (needs Supabase dashboard/CLI login). Not ready to flip to
      Complete — (1) and (2) need fixing before this can be re-run.
      FOLLOW-UP same day: user applied the migration live. Re-verified
      directly — all 4 previously-404ing resources resolve; ran a full
      live wizard flow through the exact `create_plan` ->
      `cadence_schedule.sync()` call that used to 500 (clean 200, all 7
      `cadence_schedules` rows confirmed via PostgREST); both internal
      cron endpoints (`sessions/summarize`, `notifications/scan`) now
      succeed live (200s, sane scanned/skipped/summarized counts).
      Cause 1 resolved. Cause 2 (chat.py's non-atomic ordering) is
      untouched/still latent — just not currently reachable since the
      table it failed against now exists; still worth fixing
      defensively. `pg_cron`/`pg_net` still unverified. Scenarios 9-10,
      12-13, 15, 17, ES/FR/DE still not done. Full detail in
      quickstart.md's Results section.
      SECOND FOLLOW-UP same day: sped up the time-gated scenarios by
      backdating the relevant Neo4j properties directly (via
      neo4j-driver, same package Playwright's helpers use — avoids the
      Python driver's local SSL/cert issue) instead of waiting real
      days. `behind_cadence` falls back to `Plan.created_at`; dashboard
      `is_stale` falls back to the max `CheckIn` timestamp — both just
      properties. Confirmed live: scenario 9 (gap_description exactly
      right, full pipeline runs, correctly logs skipped_no_token —
      blocked only by the known Firebase gap), 13 (3 skills scanned
      independently, no global-cap bug; separately confirmed the cap
      itself suppresses a repeat via a synthetic sent-row test), 17
      (is_stale true/false correctly split across 4 skills, live
      on-device stale badge + Continue/Revise/Start-new, no delete), 15
      (4 skills in different states on one dashboard, live), 12
      (this device is Android 9, pre-dates POST_NOTIFICATIONS —  used
      `appops set ... POST_NOTIFICATION deny` instead; no crash, and a
      fresh chat session on the still-behind skill got the coach to
      proactively raise the 15-day gap unprompted), ES/FR/DE (push copy
      + dashboard + settings all correctly localized live; clipping bug
      reproduces in all of EN/ES/FR/DE, NOT Hindi — narrows the root
      cause). Scenario 10 and 7-8's content-verification remain
      genuinely blocked by the separate Firebase/Apple push-delivery
      gap, not by time — also found while reading the code that the
      real tap-routing mechanism is `data.skill_id` off the
      notification payload, not a URL scheme, which supersedes an
      earlier failed deep-link test attempt this session. Full detail
      in quickstart.md.
      THIRD FOLLOW-UP same day: user asked to finish FCM setup. Done and
      live-verified — Firebase project + google-services.json (client
      registration) + FCM V1 service account key uploaded via
      `eas credentials` (server-side relay). Found + fixed 3 real bugs
      masked until Firebase was configured: (1) `register_token`'s
      upsert couldn't target `push_tokens`' partial unique index
      (Postgres 42P10) — every registration had silently failed since
      004 was built; fixed at the application level (select-then-branch,
      not a schema change); (2) `_send_expo_push`'s status check
      prioritized DeviceNotRegistered over a real "ok" in the same
      batch, which could mask a genuine delivery; reordered; (3) a first
      attempt at fixing (1) also touched `addPushTokenListener` and
      introduced a real infinite loop (confirmed live: 1000s of
      `POST /v1/push-tokens` in seconds) — fixed by removing that
      listener entirely rather than patching it. 308 pytest (2 new),
      tsc/eslint clean. Live end-to-end proof: real scan sent 3/3
      notifications, all arrived on-device, tapped one and it opened
      directly into the right skill session with a gap-aware coach
      opening. Scenario 10 now fully confirmed — 22/23 scenarios
      covered. Full detail in quickstart.md.
      FOURTH FOLLOW-UP same day: fixed scenario 4 (ambiguous report ->
      clarifying question, not a guess) in build_coaching_prompt, took 3
      iterations tested live against the real model each time (a
      descriptive rule alone changed nothing; a few-shot example got it
      to ask but still also logged an intent the same turn; a separate
      mechanical "asking and logging are mutually exclusive this turn"
      rule finally worked) -- confirmed live on both the original
      failing transcript and a fresh one, plus confirmed the follow-up
      (answering the question) still logs correctly afterward. Also
      tested and ruled out the text-clipping bug's two candidate causes
      (wm density override, font_scale) by resetting each live -- same
      clipping either way; left unfixed, deprioritized by the user.
      309 pytest (3 new), tsc/eslint clean. 23/23 quickstart scenarios
      now covered. Full detail in quickstart.md.
      FIFTH FOLLOW-UP same day: user flagged T019 as still showing
      incomplete. Investigating it surfaced a MAJOR previously-hidden bug
      (see T019's note) — `usePushNotifications()` crashed the entire web
      build on every route, undetected until now because no web
      Playwright spec for any 004-era feature had ever actually been run
      before today. Fixed, plus 2 more real bugs found checking blast
      radius on a full suite run: a BigInt/`Math.min` TypeError in
      progress-checkins.spec.ts, and an ambiguous `.first()` locator in
      dashboard.spec.ts (fixed via this codebase's first `testID`). Both
      are in and type/lint-clean; live re-verification of those last two
      is blocked until the daily LLM budget resets — PW1 (89/50) and PW2
      (45/50) are both over budget for 2026-07-18 purely from this
      session's own repeated wizard-completion runs (confirmed via
      `llm_usage`, not a mystery). Remains `◐`: this round didn't touch
      the two outstanding items — `routes/chat.py`'s non-atomic ordering
      (still latent, unfixed) and `pg_cron`/`pg_net` verification (still
      needs Supabase dashboard/CLI access this session doesn't have).
- [◐] T070 `specs/README.md`: update 004's status once T068/T069 both
      pass
      PARTIAL 2026-07-17: 004's row was still saying "Specified — clarify
      required," stale since before this session even started (clarify/
      plan/tasks/implementation all happened since). Updated to
      "Implemented, pending live validation" — the accurate current
      state and the same phrasing 003 used at its equivalent point — but
      deliberately NOT "Complete," since T069 hasn't run. Flip to
      Complete once T069 passes.
      UPDATE 2026-07-18: T069's partial live run found two blocking bugs
      (migration never applied live; non-atomic chat turn in
      routes/chat.py) — see T069's note and quickstart.md's Results
      section. specs/README.md's row updated to reflect this, still not
      Complete.
      UPDATE 2026-07-18 (later): row updated again to "Implemented,
      23/23 scenarios live-validated" after the scenario-4 fix. Still
      not flipped to Complete — T069 remains `◐` (chat.py ordering,
      pg_cron/pg_net unverified), and this round's T019 investigation
      added 3 more fixed bugs (web crash, BigInt, testID) with 2 of them
      still awaiting live re-verification post budget-reset.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (T001–T002)** → **Foundational (T003–T009)**: no dependencies
  between them, but both must finish before any user-story phase starts.
- **Foundational → all user stories**: T007 (CheckIn write path) is
  load-bearing for US1, US4, US7; T008 (`ProgressService`) is
  load-bearing for US2, US4, US6.
- **US1 before US4/US3/US5** (same file, sequential, not parallel):
  `prompts.py`'s `build_coaching_prompt` is extended by T013 (US1), then
  T028 (US4), then T044 (US3), then T065 (US5) — each adds a new
  paragraph of instruction without removing the last, but they must land
  in that order since each depends on the previous extension already
  being in the file.
- **US4 before US3** (same file, sequential): `context_builder.py`'s
  `build()` gains the gap description in T027 (US4) before the last-N-
  summaries addition in T043 (US3).
- **US2 before US6**: `models/progress.py` (T033) and `ProgressService`'s
  per-skill call shape are established in US2 before US6's dashboard
  (T048) composes them at coarser grain — SC-006's "always agree"
  guarantee depends on both reading the exact same code path.
- **US6 before US7**: US7's tap-to-complete affordance (T057) extends the
  dashboard card UI US6 builds (T049) — there is nothing to tap on until
  the dashboard exists.
- **T020 (migration) blocks T021, T023** (both read/write the new
  tables).
- **T025 (internal-secret auth) blocks T026, T042** (both internal
  routes).
- **T068–T070 last** — regression + exit-gate proof, run only once all
  earlier tasks are in place.

### User Story Independence Note

Despite the shared-file sequencing above (a real implementation-order
constraint), every story remains *independently testable* per its stated
Independent Test — US1 is verifiable with zero notification/dashboard
code present, US2's progress view needs only Foundational, etc. The
sequencing constraint is about which order changes must be **written** in
(so later diffs don't conflict), not about one story's user-facing
behavior depending on another's being demoed first.

---

## Parallel Example: Foundational

```bash
# Launch Foundational tests together:
Task: "pytest EXTEND test_intent_apply.py: log_checkin/report_obstacle/complete_step Cypher translation"
Task: "pytest NEW test_progress.py: streak/cadence-adherence/completed-steps fixtures"

# Launch independent Foundational implementation together:
Task: "constants.py: all FR-018 thresholds"
Task: "models/intents.py: three new intent models"
```

## Parallel Example: User Story 4

```bash
# Launch all independent US4 tests together:
Task: "pytest test_cadence_schedule.py: sync on create_plan/revise_plan"
Task: "pytest test_notifications.py: frequency cap, quiet hours, silent-skip cases, multi-week simulation"
Task: "pytest test_notifications_contract.py: push-token + rotation + internal-secret auth"
Task: "pytest EXTEND test_context_builder.py: gap description"

# Launch independent US4 services together (after T020 migration):
Task: "services/cadence_schedule.py"
Task: "services/notifications.py"
```

---

## Implementation Strategy

### MVP First (Setup + Foundational + US1)

Conversational check-ins recorded correctly is the smallest slice that
delivers real value and is fully demoable without any notification,
dashboard, or session-continuity work.

### Incremental Delivery

1. Setup + Foundational → CheckIn write path + progress read path ready.
2. US1 → conversational check-ins work end-to-end (MVP).
3. US4 → the proactive-nudge promise closes the loop (both P1 stories
   done).
4. US2 → dedicated progress view.
5. US3 → cross-session continuity.
6. US6 → home dashboard (landing-screen change).
7. US7 → tap-to-complete on the dashboard US6 just built.
8. US5 → goal-revision correctness fixes + trajectory awareness.
9. Polish → docs, full regression, live quickstart exit gate.

Commit after each phase, same "implement → verify → commit → push"
rhythm as 001–003. `pg_cron`/`pg_net` availability (research.md R1) should
be verified in the Supabase console before starting Phase 4 (US4), not
assumed.
