# Implementation Plan: Voice Layer

**Branch**: `003-voice-layer` | **Date**: 2026-07-15 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/003-voice-layer/spec.md`

## Summary

Every conversation surface (wizard and ongoing chat) gains a push-to-talk
voice mode alongside always-available text: hold to speak, see an interim
transcript live (or a "Listening…" indicator on recognizers that can't
stream partials), edit the final transcript before it sends through the
exact same `/v1/chat` pipeline as typed text. Coach replies are spoken
aloud via TTS, interruptible by the next push-to-talk press, and
independently disableable per-user. This is almost entirely a client
(`app/`) feature — voice recording, recognition, and playback all happen
on-device via `expo-speech-recognition` (STT) and `expo-speech` (TTS,
already Expo-native); the backend's only changes are threading a real
`modality` value through `/v1/chat` (currently hardcoded to `"chat"`,
per Constitution IV) and persisting the spoken-replies preference on the
existing `profiles` row (same pattern as language/display name, FR-011
precedent).

## Technical Context

**Language/Version**: unchanged — TypeScript/Expo (app), Python 3.12 (api).

**Primary Dependencies**: NEW client deps — `expo-speech-recognition`
(community package by jamsch, versioned to track Expo SDK: install
`expo-speech-recognition@57` for this app's SDK 57; ships a config plugin,
requires a native dev build, already this app's baseline per the
constitution) for STT, and `expo-speech` (official Expo SDK package,
already dev-build-compatible, also works on web via the browser's
`SpeechSynthesis` API) for TTS. No new backend dependency.

**Storage**: `messages.modality` column already exists with a
`('chat','voice')` check constraint (001 anticipated this) but is
currently hardcoded to `'chat'` server-side (`MessageStore.insert_turn`)
— 003 is the first feature to actually pass `'voice'` through. `profiles`
gains one new column, `voice_replies_enabled boolean not null default
true` (new migration), mirroring how `language`/`display_name` are
already persisted profile settings.

**Testing**: jest for new client hooks/helpers with the native module
mocked (confidence thresholding, capability-detection, transcript-cleanup
logic) since `expo-speech-recognition` requires a real device/dev build
that CI can't run; pytest for the one-line backend change (`modality`
round-trips into the stored message); Playwright against the Expo web
export using Chrome (the one mainstream desktop browser with working
Web Speech API support per research.md) for the push-to-talk UX flow;
Maestro flows for the native iOS/Android push-to-talk + TTS-interrupt
scenarios (device-dependent, same caveat as 001/002's existing Maestro
flows — see specs/README.md's "Deferred: iOS device validation").

**Target Platform**: unchanged (iOS/Android/web from one Expo codebase);
voice specifically requires the native dev build already mandated by the
constitution (no Expo Go path — `expo-speech-recognition` has no Expo Go
support, confirmed in research.md).

**Project Type**: unchanged monorepo (`app/` + `api/`).

**Performance Goals**: SC-004 (clarified 2026-07-15) — interim transcript
first render ≤300ms after speech starts; TTS playback stops ≤300ms after
a push-to-talk press interrupts it.

**Constraints**: FR-009/Constitution IX — zero incremental per-use cost
(on-device/platform recognizers only, no cloud STT vendor); FR-003 —
low-confidence prompt only fires when the platform reports a confidence
score (threshold <0.5), silently skipped otherwise (clarified); FR-002 —
interim streaming is best-effort, degrades to a "Listening…" indicator on
batch-only recognizers (clarified); STT and TTS language availability
are checked and degraded independently (clarified).

**Scale/Scope**: one new client hook (`use-voice-session.ts`), one new
capability-detection helper, `ConversationView` extended (not duplicated —
same component chat.tsx and wizard.tsx already share) with a mic
button/interim-transcript/TTS wiring, one settings toggle, one Postgres
migration, three small backend edits (ChatRequest, MessageStore, the one
route call site) — no new backend endpoints, no new Neo4j schema.

## Constitution Check

*GATE: evaluated against constitution v1.7.0 — re-checked after Phase 1.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | LLM never writes Cypher | PASS (N/A) | Voice changes nothing about intent handling — a voice-originated message becomes ordinary text before it ever reaches the LLM. |
| II | Progress derived | PASS (N/A) | No CheckIn/progress surface touched. |
| III | Goal immutable; no UI delete | PASS (N/A) | Not touched. |
| IV | Single message pipeline | PASS, and closes a gap | This feature is *why* Principle IV's modality flag exists — 001/002 never actually set it. `apply_intents`, `context_builder`, and the LLM prompts all key off message content only, never `modality` — confirmed no downstream branch needs adding. |
| V | Budgeted LLM calls | PASS | Voice messages consume the same per-user daily budget as typed ones (same `/v1/chat` call) — no new LLM call type, no separate budget bucket. |
| VI | Provider/tier config-only | PASS (N/A) | Not touched. |
| VII | Data placement | PASS | FR-009/spec Assumptions: raw audio is never persisted anywhere, on-device or server; only the user-confirmed transcript is stored, in the existing Postgres `messages` table — no new storage class. |
| VIII | Testing | PASS, flagged | `expo-speech-recognition`'s native module can't run in CI — jest covers the pure-logic pieces (confidence threshold, capability detection) with the module mocked; the actual recognizer behavior is proven live via Maestro (device) and Playwright (Chrome web, using the package's Web Speech API path) per FR-008/SC-001. This mirrors 001/002's existing device-dependent-test pattern, not a new gap. |
| IX | Cost ceiling | PASS | Both packages are $0 — on-device/platform-native recognizers and the browser's built-in `SpeechSynthesis`; FR-009 codifies this as a hard requirement. |
| X | Multilingual | PASS | STT/TTS operate in the profile language (spec Edge Cases, resolved 2026-07-12); independent per-capability availability checks (clarified 2026-07-15) mean a language gap in one capability doesn't silently break the other. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/003-voice-layer/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── contracts/
    └── api.md           # Phase 1 output
                          # tasks.md — Phase 2 (/speckit-tasks, not yet created)
```

### Source Code (repository root)

```text
api/src/skillcoach_api/
├── models/
│   ├── chat.py             # EXTEND: ChatRequest gains
│   │                       #   modality: Literal["chat","voice"] = "chat"
│   └── profile.py          # EXTEND: ProfileRequest/ProfileResponse gain
│                           #   voice_replies_enabled: bool = True
├── routes/
│   ├── chat.py              # EXTEND: pass body.modality through to
│   │                       #   MessageStore.insert_turn (currently
│   │                       #   hardcoded "chat")
│   └── profile.py           # EXTEND: _PROFILE_FIELDS gains
│                           #   "voice_replies_enabled"; upsert() call
│                           #   gains the new param
├── services/
│   ├── messages.py          # EXTEND: insert_turn(..., modality: str)
│   │                       #   replaces the hardcoded "chat" in `common`
│   └── profiles.py          # EXTEND: upsert(..., voice_replies_enabled)
└── tests/
    └── test_chat_contract.py    # EXTEND: assert a modality="voice"
                                  #   request stores that modality
                                  #   (currently only "chat" is exercised)

supabase/migrations/
└── 2026071X_voice_preference.sql   # NEW: alter profiles add
                                     #   voice_replies_enabled boolean
                                     #   not null default true

app/src/
├── hooks/
│   └── use-voice-session.ts       # NEW: wraps expo-speech-recognition
│                                  #   (start/stop/abort, interim+final
│                                  #   result events, confidence read) and
│                                  #   expo-speech (speak/stop); exposes
│                                  #   {status, interimText, start, stop}
├── lib/
│   └── voice-capabilities.ts      # NEW: per-language STT/TTS
│                                  #   availability probe (independent
│                                  #   per clarified FR-007), used by
│                                  #   use-voice-session + the mic
│                                  #   button's disabled state
├── components/
│   └── conversation-view.tsx      # EXTEND: mic button alongside the
│                                  #   text input; interim-transcript /
│                                  #   "Listening…" row; auto-speaks new
│                                  #   assistant bubbles when
│                                  #   voice_replies_enabled and stops on
│                                  #   next push-to-talk (US2)
├── app/(main)/
│   └── settings.tsx               # EXTEND: "Spoken replies" toggle,
│                                  #   same save flow as language/name
└── lib/
    ├── api.ts                    # EXTEND: postChat sends modality;
    │                             #   ProfilePayload gains
    │                             #   voice_replies_enabled
    └── supabase.ts               # EXTEND: Profile type + fetchOwnProfile
                                   #   select list gain
                                   #   voice_replies_enabled
```

**Structure Decision**: Same monorepo; no new top-level directories, no
new backend routes. Voice logic lives in two new client files
(`use-voice-session.ts`, `voice-capabilities.ts`) plus extensions to
files 002 already established (`conversation-view.tsx`, `settings.tsx`,
`api.ts`) — chat.tsx and wizard.tsx need no direct changes since they
already consume `ConversationView` and `useChatSession` without knowing
their internals.

## Implementation Notes (how the pieces connect)

1. **Voice is additive at the `ConversationView` layer, not a new
   screen.** Both chat.tsx (existing skill) and wizard.tsx (skill_id
   null) already render `ConversationView`; giving it a mic button means
   voice works identically in both without touching either screen file,
   the same "shared, not duplicated" pattern 002 established for
   send/optimistic-update logic.
2. **`use-voice-session` owns the state machine** (idle → recording →
   (transcribing) → editable-final; separately, idle → speaking →
   interrupted), not `ConversationView` itself, so it can be unit-tested
   with the native module mocked. On `stop()`, if the recognizer's final
   result carries a confidence score below 0.5, the hook exposes a
   `needsConfirmation: true` flag instead of auto-populating the send
   draft — `ConversationView` renders the existing "did you mean…"
   prompt UI already implied by US1 scenario 3. On platforms that report
   no confidence score at all, `needsConfirmation` is never set — the
   edit-before-send step (already present for every transcript,
   confidence-gated or not) is the sole correction path there, per the
   clarified FR-003.
3. **Interim results degrade at the hook boundary.** If
   `expo-speech-recognition`'s config doesn't emit any `result` event with
   `isFinal: false` within a short grace window after `start()`,
   `use-voice-session` reports `interimSupported: false` for that
   session and `ConversationView` renders a static "Listening…" row
   instead of live partial text — no separate code path in the UI layer,
   just a different value for the same `interimText`-or-indicator slot
   (clarified FR-002).
4. **`voice-capabilities.ts` is checked once per profile-language
   change**, not per recording — it asks `expo-speech-recognition` for
   locale support (STT) and `expo-speech`'s `getAvailableVoicesAsync()`
   filtered by language (TTS) independently, caching the pair. The mic
   button disables with FR-007's guidance copy when STT is unavailable;
   TTS-unavailable never disables the mic — it only suppresses
   auto-speak for that language, same code path as the user having
   spoken replies off (clarified FR-007).
5. **TTS auto-play + interrupt lives in `ConversationView`**: on a new
   assistant bubble appended (from `useChatSession`'s existing message
   list), if `voice_replies_enabled` and the language's TTS capability
   check passed, call `Speech.speak(...)`. Pressing push-to-talk always
   calls `Speech.stop()` first regardless of whether anything is
   currently speaking (idempotent no-op otherwise) — this is what makes
   US2 scenario 2's "immediate interrupt" simple: no need to track
   playback state to decide whether to stop.
6. **`modality` threads through unchanged plumbing.** `useChatSession`'s
   `send()` already accepts an override text (used today for
   suggested-reply chips); it gains a `modality` argument the mic-button
   send path passes as `"voice"` and the text-input send path passes as
   `"chat"` — `postChat` forwards it in the request body, `routes/chat.py`
   forwards `body.modality` to `MessageStore.insert_turn` instead of the
   literal `"chat"` it hardcodes today. No other file in the chat pipeline
   (context builder, LLM prompts, intent apply) reads `modality` at all,
   confirming Constitution IV's "nothing downstream branches on modality"
   holds without new work.
7. **Permissions are requested on first mic-button tap**, not at app
   launch or screen mount — `use-voice-session.start()` calls
   `ExpoSpeechRecognitionModule.requestPermissionsAsync()` lazily on its
   first invocation per app session, satisfying FR-006's "contextual"
   requirement without a separate permissions-priming screen.
8. **Voice preference persistence reuses the profile round-trip
   exactly** — `voice_replies_enabled` rides along in the same
   `ProfileRequest`/`ProfileResponse` and the same settings.tsx
   save button as `language`/`display_name` (FR-011 precedent from 001),
   rather than inventing a separate local-only (AsyncStorage) setting;
   this keeps the preference consistent across a user's devices like
   every other profile field already is.

## Complexity Tracking

No constitution violations — table intentionally empty.
