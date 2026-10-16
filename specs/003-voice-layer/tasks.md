# Tasks: Voice Layer

**Input**: Design documents from `/specs/003-voice-layer/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md, quickstart.md

**Tests**: MANDATORY (Constitution VIII) and **test-first (TDD)** per
explicit user request 2026-07-15 — every phase's Tests subsection is
ordered before its Implementation subsection, and every test task must be
written and confirmed failing before the implementation task(s) it
covers are started. Three categories apply here: unit (jest, pure logic
only — this app has no component-rendering test library installed, so
UI behavior is proven via UX-workflow tests, not jest+render), API
contract (pytest), and UX workflow (Playwright for the Expo web export,
Maestro for native — device-dependent Maestro runs stay flagged the same
way 001/002's already are, see specs/README.md's "Deferred: iOS device
validation").

**Organization**: grouped by user story from spec.md. US1 = speak instead
of type (P1), US2 = hear the coach reply (P1), US3 = permissions and
graceful denial (P2), US4 = voice on web where supported (P3).

Revised 2026-07-15 after `/speckit-analyze` (see analysis report): added
T002 (Constitution X — localized OS-level permission-prompt strings,
was zero-coverage CRITICAL), T005 (Constitution IV modality-blindness
invariant, was unguarded), T021 (Maestro TTS-interrupt, promised by
plan.md but missing), T040 (SC-002 regression-suite confirmation, was
uncovered), timing assertions in T010/T019 (SC-004's ≤300ms targets were
previously unverified), and fixed T022's migration date.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- Paths are repo-relative; structure per plan.md

---

## Phase 1: Setup

- [x] T001 Install `expo-speech-recognition` and `expo-speech` in
      `app/package.json`; add `"expo-speech-recognition"` to the
      `plugins` array in `app/app.json`. **Requires a native rebuild**
      (`npx expo prebuild` / `npx expo run:ios` / `npx expo run:android`)
      before any of this feature's native code can run — a JS-only
      reload is not enough, same caveat as 002's `app.json` keyboard fix.
- [x] T002 Localize the native OS-level permission-prompt strings across
      all 5 launch languages (Constitution X; FR-006's "OS-level usage
      descriptions MUST be localized" — analysis finding K1, was
      CRITICAL/zero-coverage). iOS mechanism: `app.json`'s
      `expo.locales` map (`{"en": "./assets/locales/en.json", "hi": ...}`)
      with `NSMicrophoneUsageDescription` + `NSSpeechRecognitionUsageDescription`
      per locale file, plus `ios.infoPlist.CFBundleAllowMixedLocalizations: true`
      — Expo generates the `.lproj` structure at build time, no custom
      config plugin needed. Android has no equivalent per-app-customizable
      OS dialog string (the system `RECORD_AUDIO` prompt is fixed OS
      copy) — Android's localization need is fully met by T034/T035's
      in-app pre-permission guidance, not by this task. New
      `app/assets/locales/{en,hi,es,fr,de}.json`, extend `app/app.json`.

---

## Phase 2: Foundational (blocks all user stories)

### Tests for Foundational (write FIRST, confirm they FAIL before implementation)

- [x] T003 [P] pytest: `ChatRequest` with `modality="voice"` stores that
      modality on both rows of the turn; omitting `modality` still
      defaults to `"chat"` (currently hardcoded — this test must fail
      against today's code) — extend `api/tests/test_chat_contract.py`
- [x] T004 [P] jest: `voice-capabilities.ts` — STT and TTS availability
      are detected and reported **independently** per language (mock
      `expo-speech-recognition`'s locale-support API and `expo-speech`'s
      `getAvailableVoicesAsync`) — new `app/src/lib/voice-capabilities.test.ts`
- [x] T005 [P] pytest: Constitution IV invariant — two otherwise-identical
      `/v1/chat` calls differing only in `modality` ("chat" vs "voice")
      produce byte-identical context/prompt construction (assert via a
      `FakeRunnable` that records what it was called with, same pattern
      as `test_chat_wizard.py`'s real-route tests) — new test in
      `api/tests/test_chat_contract.py` or `test_chat_wizard.py`. This
      test must fail today since `ChatRequest` has no `modality` field
      to construct a differing request with yet. (Locks in the
      no-downstream-branching guarantee plan.md asserts by inspection —
      analysis finding U1.)

### Foundational Implementation

- [x] T006 [P] Backend: `ChatRequest` gains
      `modality: Literal["chat", "voice"] = "chat"` in
      `api/src/skillcoach_api/models/chat.py` (satisfies part of T005)
- [x] T007 Backend: `MessageStore.insert_turn` takes a `modality` param
      (replacing the hardcoded `"chat"` in `common`); `routes/chat.py`
      passes `body.modality` through, and **only** through to
      `MessageStore` — no other service call (context builder, LLM
      prompt, intent apply) receives it — `api/src/skillcoach_api/services/messages.py`,
      `api/src/skillcoach_api/routes/chat.py` (depends on T006; satisfies
      T003 and T005)
- [x] T008 [P] Client: `voice-capabilities.ts` implementation — checks
      STT locale support and TTS voice availability independently per
      profile language, caches the pair — new `app/src/lib/voice-capabilities.ts`
      (satisfies T004)

**Checkpoint**: modality round-trips end-to-end at the API layer without
leaking into anything downstream; capability detection is available for
every story that needs it (US1, US3, US4).

---

## Phase 3: User Story 1 - Speak instead of type (Priority: P1) 🎯 MVP

**Goal**: Push-to-talk voice input works in any conversation (wizard or
existing skill chat), producing a message record identical to a typed one
except `modality: voice`.

**Independent Test**: Hold the mic button in an existing conversation,
speak, release, edit if needed, send — verify a normal coach reply and a
`messages` row with `modality: voice`.

### Tests for User Story 1 (write FIRST, confirm they FAIL before implementation)

- [x] T009 [P] [US1] jest: pure helper functions exported from
      `use-voice-session.ts` — `shouldPromptConfirmation(confidence)`
      (fires only below 0.5, `undefined` never fires it per the clarified
      FR-003) and `resolveInterimMode(supportsInterim)` (interim text vs.
      "Listening…" indicator, clarified FR-002) — new
      `app/src/hooks/use-voice-session.test.ts`
- [x] T010 [P] [US1] Playwright: push-to-talk send flow on Chrome —
      `page.addInitScript` stubs `window.SpeechRecognition` to emit
      deterministic interim + final `result` events (real STT accuracy
      is out of scope; app behavior in response to events is what's
      under test), verify live interim text renders, final transcript is
      editable, and sending stores `modality: voice`. **Also assert
      timing**: capture the timestamp of the stubbed interim event and
      the timestamp interim text first paints in the DOM, assert the gap
      is ≤300ms (SC-004) — new `app/e2e/playwright/tests/voice.spec.ts`
- [x] T011 [P] [US1] Maestro: native push-to-talk flow (hold, speak,
      release, edit, send) — new `app/.maestro/flows/voice-push-to-talk.yaml`.
      **Run live 2026-07-16 on a physical OnePlus 3 (Android 9, API 28)
      — found and fixed a CRITICAL real bug in the process**:
      `getSupportedLocales()` is unreliable not just on web but on
      **any Android device below API 31** (documented in the package's
      own source: "Not supported on Android 12 and below"), which was
      permanently disabling the mic on this device for a supported
      language. Fixed in `voice-capabilities.ts`
      (`resolveSttAvailability` + `isLocaleListReliable`, using
      `expo-device`'s `platformApiLevel`) and confirmed live via
      screenshot: the mic went from permanently disabled
      ("Voice isn't available on this device right now") to enabled.
      That session's scripted Maestro flow never completed a full clean
      run end-to-end (this device's cold-boot time is real but wildly
      variable — 20s to 60s+ — causing the flow's own timeouts to fire
      unpredictably; a device-performance/Maestro-driver characteristic,
      not an app bug).
      **Completed live 2026-07-17**: Metro dev-client bundler wasn't
      running this time either (needed for the native build to get past
      its splash screen — unrelated to the above bug); once started, ran
      the full flow end-to-end with real speech ("I want to learn to
      swim"), edited the transcript to "...swim well", and sent it —
      confirmed both in the UI and via a direct `messages` table query
      (`modality: 'voice'`, content matching the edited text exactly).
      The `maestro test` CLI itself is still flaky on this device over
      wireless ADB (gRPC `DEADLINE_EXCEEDED` on long-lived sessions), so
      this was confirmed by driving the flow directly via adb/hierarchy
      inspection rather than a green CLI exit code — same characteristic
      as before, not an app bug.

### Implementation for User Story 1

- [x] T012 [US1] `use-voice-session.ts` core hook: wraps
      `ExpoSpeechRecognitionModule` start/stop/abort, handles interim vs.
      final `result` events, applies the confidence gate and interim
      degrade helpers from T009 — new `app/src/hooks/use-voice-session.ts`
      (depends on T008)
- [x] T013 [US1] `useChatSession.send` gains a `modality` argument
      (`'chat' | 'voice'`), forwarded to `postChat` — extend
      `app/src/hooks/use-chat-session.ts`
- [x] T014 [US1] `postChat` sends `modality` in the request body — extend
      `app/src/lib/api.ts` (depends on T013)
- [x] T015 [US1] `ConversationView`: mic button; interim transcript /
      "Listening…" row; editable final transcript with a low-confidence
      confirm prompt when `shouldPromptConfirmation` fires; wires the mic
      send path to `send(text, 'voice')` — extend
      `app/src/components/conversation-view.tsx` (depends on T012, T014)
- [x] T016 [P] [US1] i18n strings for the mic button, listening
      indicator, and low-confidence confirm prompt across all 5 launch
      locales — `app/src/i18n/`

**Checkpoint**: US1 fully functional and independently testable — voice
send works end to end in both chat.tsx and wizard.tsx for free, since
both already consume `ConversationView`/`useChatSession` without knowing
their internals.

---

## Phase 4: User Story 2 - Hear the coach reply (Priority: P1)

**Goal**: Coach replies are spoken aloud, interruptible by the next
push-to-talk press, and disableable via a persisted per-user preference.

**Independent Test**: Send any message, hear the reply spoken; press
push-to-talk mid-playback and confirm speech stops instantly; disable
spoken replies in Settings and confirm replies render text-only
thereafter.

### Tests for User Story 2 (write FIRST, confirm they FAIL before implementation)

- [x] T017 [P] [US2] pytest: `POST /v1/profile` with
      `voice_replies_enabled: false` persists and round-trips; omitting
      it defaults to `true` — extend `api/tests/test_profile_contract.py`
- [x] T018 [P] [US2] jest: `use-voice-session`'s `speak()`/`stop()` and
      the "unconditional stop on start" interrupt rule (mock
      `expo-speech`) — extend `app/src/hooks/use-voice-session.test.ts`
- [x] T019 [P] [US2] Playwright: spy on `window.speechSynthesis.speak`
      to verify a new assistant reply auto-speaks when
      `voice_replies_enabled` is true and stays silent when false;
      verify a push-to-talk press cancels in-progress speech immediately.
      **Also assert timing**: capture the timestamp of the push-to-talk
      press and of the `speechSynthesis.cancel()`/stop call, assert the
      gap is ≤300ms (SC-004) — extend `app/e2e/playwright/tests/voice.spec.ts`
- [x] T020 [P] [US2] Playwright: "Spoken replies" toggle in Settings
      persists across reload — extend `app/e2e/playwright/tests/foundations.spec.ts`
      (same pattern as the existing language/display-name settings coverage)
- [x] T021 [P] [US2] Maestro: native TTS-interrupt flow — trigger a
      spoken reply, press push-to-talk mid-playback, assert playback
      stops immediately and recording starts — new
      `app/.maestro/flows/voice-tts-interrupt.yaml`. Device-dependent,
      same deferred-if-unavailable handling as T011. (plan.md's Testing
      section named this scenario explicitly; it was missing from the
      original task breakdown — analysis finding I1.)
      **Run live 2026-07-17** on the same OnePlus 3: sent a voice message,
      coach reply began speaking, pressed the mic mid-reply — logcat
      confirmed a fresh `Start recognition` call fired immediately
      (unconditional `Speech.stop()` per T027), and the user (physically
      present) confirmed audio stopped instantly with no lingering/overlap.
      The scripted `maestro test` CLI itself still hit the same
      gRPC-driver flakiness documented under T011 on this device; this
      flow was confirmed by direct interaction, not a clean CLI exit.

### Implementation for User Story 2

- [x] T022 [US2] Migration: `profiles.voice_replies_enabled boolean not
      null default true` — new `supabase/migrations/20260716000001_voice_preference.sql`
      (dated to the day this task was actually implemented, matching
      001's convention of dating a migration to when it's authored —
      analysis finding I2 flagged the plan-time date as premature; the
      real implementation session landed on 2026-07-16)
- [x] T023 [P] [US2] Backend: `ProfileRequest`/`ProfileResponse` gain
      `voice_replies_enabled: bool = True` —
      `api/src/skillcoach_api/models/profile.py`
- [x] T024 [US2] Backend: `ProfileStore.upsert` takes
      `voice_replies_enabled`; `routes/profile.py`'s `_PROFILE_FIELDS`
      and the `upsert()` call site include it —
      `api/src/skillcoach_api/services/profiles.py`,
      `api/src/skillcoach_api/routes/profile.py` (depends on T022, T023;
      satisfies T017)
- [x] T025 [P] [US2] Client: `Profile` type and `fetchOwnProfile`'s
      select list gain `voice_replies_enabled` — `app/src/lib/supabase.ts`
- [x] T026 [P] [US2] Client: `ProfilePayload` and `postProfile` gain
      `voice_replies_enabled` — `app/src/lib/api.ts`
- [x] T027 [US2] `use-voice-session.ts` gains `speak()`/`stop()`; `start()`
      unconditionally calls `Speech.stop()` first (idempotent no-op if
      nothing is speaking) — extend `app/src/hooks/use-voice-session.ts`
      (depends on T012; satisfies T018)
- [x] T028 [US2] `ConversationView`: auto-speaks new assistant bubbles
      when `voice_replies_enabled` and the language's TTS capability
      check passes — extend `app/src/components/conversation-view.tsx`
      (depends on T027)
- [x] T029 [US2] `settings.tsx`: "Spoken replies" toggle, same save flow
      as language/display name — extend `app/src/app/(main)/settings.tsx`
      (depends on T025, T026)

**Checkpoint**: US1 + US2 both work independently — full voice
round-trip (speak in, hear reply, interrupt, disable) is functional.

---

## Phase 5: User Story 3 - Permissions and graceful denial (Priority: P2)

**Goal**: Mic/speech permissions are requested contextually; every
denial or unavailability state leaves chat fully usable with clear
guidance.

**Independent Test**: Deny mic permission, confirm the voice control
shows a disabled state with guidance, complete the same conversation by
chat.

### Tests for User Story 3 (write FIRST, confirm they FAIL before implementation)

- [x] T030 [P] [US3] jest: mic-disabled-state decision logic covering
      permission-denied, recognizer-unavailable, and
      STT-unavailable-for-language cases — extend
      `app/src/lib/voice-capabilities.test.ts`
- [x] T031 [P] [US3] Playwright: deny mic permission via the browser
      context, verify the mic control shows a disabled state with
      guidance and chat remains fully functional — extend
      `app/e2e/playwright/tests/voice.spec.ts`
- [x] T032 [P] [US3] Maestro: native permission-denial flow — new
      `app/.maestro/flows/voice-permission-denied.yaml` (device-dependent,
      same deferred-if-unavailable handling as T011)
      **Run live 2026-07-17**: found and fixed two real bugs in the
      process — (1) Maestro auto-grants runtime permissions by default,
      which was silently defeating the flow's "tap Don't Allow" step on
      every run; fixed via `launchApp: permissions: microphone: deny`
      instead of relying on a live dialog tap. (2) the post-sign-in
      `extendedWaitUntil: visible: "Skill Coach"` raced the sign-in
      screen's own branding text (same string, different screen) and
      intermittently false-passed before real navigation landed; fixed to
      wait on "Add skill" instead (also applied to
      `voice-push-to-talk.yaml`). After both fixes, drove the flow live:
      real OS "Allow Skill Coach to record audio?" dialog appeared, denied
      it, exact `permissionDeniedGuidance` copy rendered, and text chat
      still sent successfully. The `maestro test` CLI itself remained
      flaky on this device (gRPC driver timeouts, see T011); final
      confirmation was via direct interaction, not a green CLI exit.

### Implementation for User Story 3

- [x] T033 [US3] `use-voice-session.ts`: calls
      `requestPermissionsAsync()` contextually on the first `start()`
      call only (not at mount/app-launch); exposes permission and
      availability status — extend `app/src/hooks/use-voice-session.ts`
      (depends on T012)
- [x] T034 [US3] `ConversationView`: disabled mic state with guidance
      copy, distinguishing denied vs. unavailable vs.
      STT-unsupported-for-language — extend
      `app/src/components/conversation-view.tsx` (depends on T033)
- [x] T035 [P] [US3] i18n strings for denial/unavailable in-app guidance
      across all 5 launch locales (distinct from T002's native
      OS-permission-dialog strings — this is the app's own follow-up
      copy shown after the OS decision) — `app/src/i18n/`

**Checkpoint**: US1–US3 all independently functional — permission denial
degrades gracefully everywhere voice is offered.

---

## Phase 6: User Story 4 - Voice on the web where supported (Priority: P3)

**Goal**: Push-to-talk works on Chrome desktop; unsupported browsers hide
the voice control and fall back to chat cleanly.

**Independent Test**: Complete a voice exchange in Chrome; open an
unsupported browser and confirm the UI degrades to chat cleanly.

### Tests for User Story 4 (write FIRST, confirm they FAIL before implementation)

- [x] T036 [P] [US4] Playwright: simulate an unsupported browser (no
      `SpeechRecognition`/`webkitSpeechRecognition` global) — verify the
      mic control is hidden/disabled and chat is fully functional —
      extend `app/e2e/playwright/tests/voice.spec.ts`. (Chrome's
      supported-browser path needs no separate test here — T010 and T019
      already run on Chrome and prove it.)

### Implementation for User Story 4

- [x] T037 [US4] Web browser-support detection — **turned out to need no
      new code**: `ExpoSpeechRecognitionModule.isRecognitionAvailable()`
      (already used by `checkSttAvailable` since T008) checks
      `typeof webkitSpeechRecognition !== "undefined" || typeof
      SpeechRecognition !== "undefined"` on web — the exact same signal
      an unsupported browser trips. `resolveMicDisabledReason` (T030) and
      `ConversationView`'s disabled-mic rendering (T034) already handle
      the resulting `stt: false` correctly; T036's test verifies this
      existing wiring covers FR-008's browser-support case, not just the
      native "recognizer unavailable" case it was originally written for.

**Checkpoint**: All four user stories independently functional.

---

## Phase 7: Polish & Cross-Cutting

- [x] T038 [P] `api/README.md`: document the `ChatRequest.modality` and
      `ProfileRequest.voice_replies_enabled` additions
- [x] T039 `docs/testing.md`: add 003's test index entries (unit,
      contract, UX-workflow) and a manual checklist entry for any
      Maestro flow not yet run on a device (T011, T021, T032 if deferred)
- [x] T040 Done 2026-07-16, live: `api/tests` (pytest, 191) and app
      `jest` (25) green throughout. `foundations.spec.ts` (001) and
      `smoke.spec.ts` all pass live against the deployed stack.
      `wizard-plan.spec.ts` (002) passed earlier in the same session but
      failed on a later re-run purely from PW2 exhausting its daily LLM
      budget (80/50 calls, from this session's own repeated test runs,
      confirmed via `llm_usage` table query) — not a code regression;
      re-run once the daily quota resets (UTC) for a clean confirmation
      if desired.
- [x] T041 Run all 12 `quickstart.md` scenarios live — feature exit gate
      (Constitution VIII; SC-001, SC-003–SC-005) — record a Results
      section in quickstart.md. **Done 2026-07-17**: all 12 scenarios
      confirmed (10 live on-device/browser, 2 via targeted existing
      automated coverage — see quickstart.md's Results section for the
      full breakdown and the two Maestro-flow bugs found and fixed along
      the way). Metro bundler needed to be started manually this session
      (dev-client build requires it; wasn't running) — the device was
      otherwise stuck on the splash screen with an "Unable to load
      script" error, unrelated to any app code.
- [x] T042 `specs/README.md`: **do not** mark 003 Complete until T040
      and T041 actually pass — updated to an honest "Implemented,
      pending live validation" status instead 2026-07-16, listing
      exactly what remains so a future session (or a live run right
      now) can close it out without re-deriving what's left.
      **Done 2026-07-17**: T040 and T041 both pass — updated to Complete.

---

## Dependencies & Execution Order

- **Setup (T001–T002) → Foundational (T003–T008)**: the native rebuild
  and packages must exist before any voice code compiles; T002's locale
  files are independent of T001 but land in the same phase since both
  touch `app.json`.
- **Foundational → all user stories**: T007 (modality plumbing) and T008
  (capability detection) are load-bearing for US1; T008 is also used
  directly by US3 and US4. T005's invariant test depends on T006/T007
  existing to pass, but is written first per TDD.
- **US1 before US2/US3/US4**: `use-voice-session.ts` and
  `ConversationView`'s mic button (T012, T015) are the base every later
  story extends — US2 adds TTS to the same hook/component (T027, T028),
  US3 adds permission handling to the same hook/component (T033, T034),
  US4 adds browser-support gating to the same capability helper (T037).
  This mirrors 002's "US1 before US2" precedent (nothing to extend until
  the base exists) rather than true story independence.
- **T022 (migration) blocks T024**; **T023 blocks T024**.
- **T040/T041 near-last** — regression + exit-gate proof, run only once
  T001–T037 are all in place. **T042 last.**

## Implementation Strategy

MVP slice = Setup + Foundational + US1 (voice input works, even without
spoken replies yet). Phase 4 (US2) completes the "hands-free" promise
with TTS. Phase 5 (US3) hardens the permission/denial paths a real device
will hit immediately. Phase 6 (US4) is the smallest phase — mostly a
negative-path test, since Chrome's positive path is already proven by
US1/US2's own Playwright coverage. Commit after each phase, same
"implement → verify → commit → push" rhythm as 001/002. Every phase's
tests are written and confirmed failing before that phase's
implementation tasks begin — do not implement ahead of its tests.
