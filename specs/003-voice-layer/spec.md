# Feature Specification: Voice Layer

**Feature Branch**: `003-voice-layer`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "Users can hold a button, speak, see/correct their transcript, and hear the coach's reply — full sessions hands-free-capable on iOS and Android; chat remains available everywhere."

## Clarifications

### Session 2026-07-15

- Q: SC-004 says interim transcript appears with "no perceptible delay" and TTS interruption is "immediate" — both vague. What's the quantified target for each? → A: ≤300ms for both interim-transcript-first-appears and TTS-stop-on-interrupt (standard "feels live" threshold).
- Q: FR-003's "low-confidence" prompt has no defined threshold, and some platform recognizers report no confidence score at all — how should this be handled? → A: Best-effort — threshold when the platform reports confidence (≥0.5 triggers the prompt), silently skip the prompt where no score is reported; edit-before-send remains the backstop on every platform.
- Q: FR-002 requires interim transcription to render live as a hard requirement, but some recognizers are batch-only and never stream partial results — hard gate to chat fallback, or degrade gracefully? → A: Graceful degrade — show a "Listening…" indicator when interim streaming isn't supported, final transcript still appears normally on release.
- Q: The language-support edge case bundles STT and TTS availability together, but a device can have one without the other for a given language — degrade independently or bundled? → A: Independent degrade — STT-unavailable falls back to chat as already specified; TTS-unavailable still allows voice input, that reply just renders text-only (same as the existing spoken-replies-disabled path).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Speak instead of type (Priority: P1)

In any coaching conversation, the user holds a push-to-talk button and speaks. While
speaking, they see a live interim transcript. On release, the final transcript is
shown for a moment where it can be edited, then sent through the exact same
conversation pipeline as a typed message.

**Why this priority**: Voice input is the product's headline interaction; a
swimmer at the pool or a runner mid-cooldown cannot comfortably type.

**Independent Test**: In an existing conversation on a physical device, hold the
button, say "I practiced my breathing drills today", release, and verify the
transcript appears, is editable, sends, and produces a normal coach reply.

**Acceptance Scenarios**:

1. **Given** an open conversation with mic permission granted, **When** the user
   holds the push-to-talk button and speaks, **Then** an interim transcript renders
   live while they speak.
2. **Given** the user releases the button, **When** the final transcript is ready,
   **Then** the user can edit it before it is sent, and sending produces the same
   behavior as a typed message.
3. **Given** speech recognition reports low confidence, **When** the transcript is
   presented, **Then** the user is prompted to confirm or correct ("did you mean…")
   before send.
4. **Given** a message sent by voice, **When** the message record is inspected,
   **Then** it is identical to a chat message except its modality attribute reads
   `voice` (Constitution IV).

---

### User Story 2 - Hear the coach reply (Priority: P1)

The coach's responses are spoken aloud. If the user starts a new push-to-talk while
the coach is speaking, playback stops immediately — the user can always interrupt.

**Why this priority**: Voice input without spoken output still forces eyes on the
screen; the pair is what makes hands-free sessions real.

**Independent Test**: Send any message with voice output enabled, hear the reply
spoken; press push-to-talk mid-playback and confirm speech stops instantly.

**Acceptance Scenarios**:

1. **Given** a coach reply arrives during a voice session, **When** it renders,
   **Then** it is also spoken aloud.
2. **Given** the coach is speaking, **When** the user presses push-to-talk, **Then**
   playback stops immediately and recording starts.
3. **Given** a user who prefers silence, **When** they disable spoken replies,
   **Then** replies render as text only, and the setting persists.

---

### User Story 3 - Permissions and graceful denial (Priority: P2)

The app requests microphone/speech permissions at the moment of first voice use,
explains why, and remains fully usable via chat if the user declines.

**Why this priority**: Permission denial is a guaranteed real-world path; a dead-end
here loses the user entirely, and chat fallback is a constitutional guarantee.

**Independent Test**: Deny mic permission, confirm the voice button communicates the
disabled state with a path to settings, and complete the same conversation by chat.

**Acceptance Scenarios**:

1. **Given** first voice use, **When** the user is prompted for permissions, **Then**
   the request is contextual (triggered by their tap, with a plain-language reason).
2. **Given** permissions denied, **When** the user views the conversation, **Then**
   chat works fully and the voice control shows a clear disabled state with guidance
   to re-enable in settings.
3. **Given** speech recognition is unavailable on the device (no recognizer, no
   network where one is required), **When** the user tries voice, **Then** the app
   explains the limitation and falls back to chat without crashing.

---

### User Story 4 - Voice on the web where supported (Priority: P3)

On a supported desktop browser, the same push-to-talk flow works; on unsupported
browsers, the voice control is hidden or disabled and chat is offered.

**Why this priority**: Web parity is valuable but secondary to the two mobile
platforms, which are the hands-free use cases.

**Independent Test**: Complete a voice exchange in a supported browser; open an
unsupported browser and confirm the UI degrades to chat cleanly.

**Acceptance Scenarios**:

1. **Given** a supported browser, **When** the user uses push-to-talk, **Then**
   transcription and spoken replies work end to end.
2. **Given** an unsupported browser, **When** the conversation opens, **Then** voice
   affordances are absent/disabled and chat is fully functional.

---

### Edge Cases

- User holds the button but says nothing → empty/near-empty transcript is discarded
  with gentle feedback, nothing is sent.
- Very long utterance (recognizer time limits) → recording ends at the platform
  limit, partial transcript is preserved and editable; user informed they were cut
  off.
- Incoming interruption (phone call, another app takes audio focus) mid-recording or
  mid-playback → session recovers to idle state; no stuck recording indicator.
- Noisy environment / garbled transcript → correction UX (edit before send, low
  confidence prompt) is the mitigation; the user can always fall back to typing.
- Recognition/TTS language follows the user's preferred language (Constitution X;
  resolved 2026-07-12): STT and TTS operate in the profile language across the
  launch set (EN, HI, ES, FR, DE). STT and TTS availability are checked
  independently per language: if the device lacks STT support for the profile
  language, the app says so plainly and falls back to chat; if only TTS support
  is missing, voice input still works and replies render text-only for that
  language (same behavior as spoken replies being disabled).
- Rapid re-press of push-to-talk immediately after release → previous utterance is
  finalized or discarded deterministically; no interleaved transcripts.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Every conversation surface MUST offer push-to-talk voice input on iOS
  and Android, alongside always-available text chat.
- **FR-002**: Interim transcription MUST render live during speech when the
  platform's recognizer supports streaming partial results; on recognizers
  that are batch-only (no partials), a "Listening…" indicator MUST render
  instead. Final transcript MUST be user-editable before send in both cases.
- **FR-003**: Low-confidence recognitions (confidence score < 0.5, when the
  platform's recognizer reports one) MUST trigger a confirmation/correction
  prompt before send. On platforms/recognizers that report no confidence
  score at all, the prompt is skipped for that platform — edit-before-send
  remains available as the correction path regardless.
- **FR-004**: Coach replies MUST be speakable aloud, MUST stop immediately when the
  user starts a new push-to-talk, and MUST be user-disableable (persisted
  preference).
- **FR-005**: Voice-originated messages MUST produce message records identical to
  chat messages except for `modality: voice`; no downstream component may branch on
  modality (Constitution IV).
- **FR-006**: Microphone/speech permissions MUST be requested contextually with an
  explanation; every denial or unavailability state MUST leave chat fully
  functional and communicate how to enable voice. Permission prompts and OS-level
  usage descriptions MUST be localized in all launch languages (Constitution X).
- **FR-007**: Speech-recognition (STT) and speech-synthesis (TTS) availability
  MUST each be detected at runtime, independently, per device **and per
  language** (the user's preferred language, Constitution X). STT unavailable
  for the profile language degrades to chat without error dialogs, with a
  plain notice naming the limitation. TTS unavailable for the profile
  language does not block voice input — that turn's reply renders text-only,
  same as the user-disabled spoken-replies preference (FR-004).
- **FR-008**: On the web, voice MUST work in at least one mainstream desktop
  browser and degrade gracefully (hidden/disabled control + chat) elsewhere.
- **FR-009**: Voice features MUST NOT introduce any per-use cost (on-device or
  platform-provided speech services only) (Constitution IX).

### Key Entities

- **Message (extended)**: Unchanged from feature 001 except the modality attribute
  now takes the value `voice` for voice-originated messages. The stored text is the
  user-confirmed transcript, not the raw recognizer output.
- **Voice preference**: Per-user persisted setting for spoken replies (on/off).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A complete wizard intake and a complete coaching session can each be
  performed end-to-end using only voice (hands on mic button only) on a physical
  iOS device and a physical Android device.
- **SC-002**: Chat-mode regression suite from features 001–002 passes unchanged —
  voice introduces zero behavioral differences downstream of message creation.
- **SC-003**: All permission-denied, recognizer-unavailable, and offline states are
  demonstrably recoverable: tested paths end in working chat, never a dead end or
  crash.
- **SC-004**: Interim transcript first renders within 300ms of speech starting
  (feels live), and TTS playback stops within 300ms of push-to-talk press
  (no lingering audio).
- **SC-005**: Voice runs at $0 incremental cost per session.

## Assumptions

- Push-to-talk (hold to speak) is the v1 interaction; continuous hands-free
  listening and barge-in are explicitly v2.
- On-device/platform recognizers are good enough with the correction UX as backstop;
  no cloud STT vendor is added in v1.
- Transcription quality varies by Android device; runtime detection + chat fallback
  is the accepted mitigation, not device-specific tuning.
- The raw audio is not retained; only transcripts persist (relational store, per
  Constitution VII).
