# Phase 0 Research — Voice Layer

## R1: STT package choice and SDK 57 compatibility

**Decision**: `expo-speech-recognition` (community package, github.com/jamsch/expo-speech-recognition). Resolved via `npx expo install` (SDK-57-aware) to `^56.0.1` — the package's latest published release; no `57.x` tag exists on npm yet, but its `peerDependencies` are wildcard (`expo: '*'`) and `expo install` confirmed it as the compatible pick for this SDK.

**Rationale**: This is the exact package named in the constitution's
Architectural Constraints and `docs/skill-coach-development-plan.md`
Section 1. Confirmed still current and maintained: from SDK 56 onward its
versioning tracks Expo SDK versions directly (install
`expo-speech-recognition` for SDK 57, no special tag needed — special
`@sdk-51`/`@sdk-50` tags are only for older SDKs this app isn't on). It
ships a config plugin (`"expo-speech-recognition"` in `app.json`'s
`plugins` array) that adds `RECORD_AUDIO` + Google Speech Recognition
package-visibility filtering on Android, and microphone + speech
recognition `InfoPlist` entries on iOS.

**Alternatives considered**: No alternative was seriously evaluated —
the constitution already mandates this package by name (an architectural
constraint requiring human approval to change), and no first-party Expo
STT module exists as of SDK 57.

## R2: Interim results, confidence, and platform variance

**Decision**: Consume the package's `result` event
(`{results: [{transcript, confidence, segments}], isFinal}`); treat
`isFinal: false` events as interim, `isFinal: true` as the transcript to
present for edit/send. Both the confidence-threshold behavior (FR-003)
and the interim-streaming behavior (FR-002) were clarified 2026-07-15 to
degrade gracefully rather than assume uniform platform support, because:

- **Confidence**: the package's own docs flag iOS as typically returning
  "one final result" with sparse/no confidence scoring, while Android's
  `SpeechRecognizer` generally does report confidence. A hard requirement
  to always show the low-confidence prompt would either misfire
  constantly on Android or never fire on iOS.
- **Interim streaming**: `interimResults: true` must be requested, and
  even then, availability is Android-recognizer-dependent — not every
  OEM's `SpeechRecognizer` implementation streams partials.

**Alternatives considered**: A hard per-platform capability table baked
into the client (e.g. "assume iOS never has confidence") was rejected —
runtime detection per the actual event stream is more robust than
hardcoding platform assumptions that could change with OS/package
updates.

## R3: TTS package and web support

**Decision**: `expo-speech` (official Expo SDK package, no config plugin
needed — already ships in the SDK). `Speech.stop()` interrupts and clears
the queue immediately (used for the push-to-talk interrupt, US2 scenario
2); `Speech.speak()` / `getAvailableVoicesAsync()` (filtered by BCP-47
language tag) drive playback and the TTS half of the capability check.

**Rationale**: `expo-speech` officially supports iOS, Android, *and* web
(confirmed on the current Expo docs) — on web it wraps the browser's
native `SpeechSynthesis`/`SpeechSynthesisUtterance` APIs, so no
web-specific fallback code is needed for TTS (unlike STT, where web
support comes from the community package's own polyfill, see R4). One
caveat carried into the quickstart: `expo-speech` produces no sound on
iOS physical devices in silent mode — a device-testing gotcha, not a
code concern.

**Alternatives considered**: None — this is the constitution-mandated
package and is Expo-first-party, unlike the STT side.

## R4: Web platform support and Playwright testability

**Decision**: Voice on web relies on `expo-speech-recognition`'s bundled
`ExpoWebSpeechRecognition` class, a Web Speech API polyfill/wrapper — this
is what makes `Platform.OS === 'web'` builds get a working mic button at
all. Confirmed working on Chrome desktop (the constitution/spec's named
"one mainstream desktop browser," FR-008); Chrome-on-iOS and Firefox are
explicitly unsupported by the package itself, consistent with
FR-008's "hidden/disabled + chat" fallback requirement for unsupported
browsers.

**Rationale**: Chrome desktop's native Web Speech API support means
Playwright (which drives Chromium) can exercise the real push-to-talk
flow end-to-end on web — no need to mock speech recognition in the E2E
suite the way jest has to mock the native module for unit tests.

**Alternatives considered**: Testing voice exclusively via Maestro
(device-only) was rejected — it would leave the web platform's FR-008
requirement with no automated coverage at all, contradicting Constitution
VIII.

## R5: Native dev build requirement

**Decision**: No change to this app's existing dev-build requirement —
`expo-speech-recognition` requires a native dev build and has no Expo Go
support (confirmed: "Cannot find native module" is the documented Expo Go
failure mode). This app has required dev builds since 001 for exactly
this reason (voice was always the anticipated driver), so 003 introduces
no new build-process change, just the first feature that actually needs
it.

## R6: Backend `modality` gap

**Decision**: `messages.modality` has carried a `('chat','voice')` check
constraint since 001's migration, but `MessageStore.insert_turn` (`api/src/skillcoach_api/services/messages.py`) hardcodes `"modality": "chat"` in
every insert — `ChatRequest` has never had a `modality` field. 003 is the
feature that closes this gap: add `modality: Literal["chat","voice"] =
"chat"` to `ChatRequest`, thread it through `routes/chat.py` into
`insert_turn`.

**Rationale**: This was clearly anticipated (the column and its
constraint predate this feature) rather than an oversight to second-guess
— 003 is exactly the first feature with a voice-originated message to
send.

## R7: Voice preference storage

**Decision**: Persist `voice_replies_enabled` as a new `profiles` column
(default `true`), extending the existing `ProfileRequest`/
`ProfileResponse` round-trip and settings.tsx's save flow — the same
mechanism 001's FR-011 fix already established for `language` and
`display_name`.

**Alternatives considered**: A client-only (AsyncStorage) toggle was
considered and rejected — every other user-facing preference in this app
(language, display name) is a server-persisted profile field so it
survives reinstalls/device switches; a voice-only local exception would
be an inconsistent pattern for no stated benefit.
