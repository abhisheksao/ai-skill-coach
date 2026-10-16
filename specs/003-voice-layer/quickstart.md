# Quickstart — 003 Voice Layer

Validation guide. Builds on 001/002's quickstart (same env, same running
stack) — only what's new is covered here. Voice requires a native dev
build (`npx expo run:ios` / `npx expo run:android`) — a plain `expo
start` + Expo Go session cannot exercise any of these scenarios except
where noted "web only."

## Prerequisites

Everything from 001/002's quickstart, already live. New: a physical or
simulated iOS/Android device (or Chrome desktop for web scenarios) with
microphone access; a fresh dev build after adding the
`expo-speech-recognition` config plugin (JS-only reload is insufficient —
this is a native module).

## Validation scenarios

| # | Scenario | Expected | Proves |
|---|----------|----------|--------|
| 1 | Open any conversation (wizard or existing skill's chat), hold the mic button, say a short sentence | Interim transcript renders live within ~300ms of speaking (or a "Listening…" indicator if the device's recognizer doesn't stream partials) | US1 scenario 1, SC-004, FR-002 |
| 2 | Release the button | Final transcript shown, editable; edit it, then send | US1 scenario 2 |
| 3 | Sent voice message → inspect the stored row (Supabase `messages` table) | `modality = 'voice'`; `content` matches the edited (not raw) transcript; row is otherwise identical in shape to a chat-sent row | US1 scenario 4, FR-005 |
| 4 | Coach reply arrives after a voice message | Reply text also spoken aloud (unless spoken replies are off in Settings) | US2 scenario 1 |
| 5 | While the coach is speaking, press push-to-talk again | Playback stops immediately (≤300ms, no lingering audio), recording starts | US2 scenario 2, SC-004 |
| 6 | Settings → disable "Spoken replies" → send another voice message | Reply renders text-only; setting persists across app restart (re-fetch profile) | US2 scenario 3, FR-004 |
| 7 | Deny mic permission when first prompted | Voice control shows a disabled state with guidance to re-enable in device settings; chat still fully works | US3 scenario 1–2, FR-006 |
| 8 | Hold the button and say nothing, release | Empty/near-empty transcript discarded with gentle feedback; nothing sent | Edge case: silent hold |
| 9 | Web (Chrome desktop): open a conversation, use push-to-talk | Full transcription + spoken reply works, same as native | US4 scenario 1, FR-008 |
| 10 | Web (a browser other than Chrome desktop, e.g. Firefox or Safari) | Mic control hidden/disabled; chat fully functional | US4 scenario 2, FR-008 |
| 11 | Simulate a language with no on-device TTS voice installed for the profile language (or a language the device genuinely lacks) | STT still works if available; that reply renders text-only rather than blocking voice input entirely | Clarification: independent STT/TTS degrade, FR-007 |
| 12 | Rapid re-press of push-to-talk immediately after release | Previous utterance finalized or discarded deterministically; no interleaved/garbled transcripts | Edge case: rapid re-press |

Language sampling (Constitution VIII): run scenarios 1–6 in English and
Hindi in full; for Spanish/French/German, confirm STT transcribes and TTS
speaks back correctly in that language (smoke — a single short exchange
per language is sufficient, consistent with 002's sampling policy).

## Results

Run live 2026-07-17 on a physical OnePlus 3 (Android 9, API 28, wireless
ADB) plus Chrome (Playwright, headed against a fresh `expo export --web`
build). Two real bugs were found and fixed in the process (see below).

| # | Scenario | Result |
|---|----------|--------|
| 1 | Interim transcript renders live | ✅ live speech — `onPartialResults` fired within ~100-300ms per word (logcat timestamps), rendered in the editable field |
| 2 | Release → editable final transcript, edit, send | ✅ live — "I want to learn to swim" spoken, edited to "...swim well", sent |
| 3 | Stored row `modality='voice'`, content matches edited text | ✅ verified directly via `messages` table query (service-role REST) — `modality` correctly varies per-message (`voice` for spoken turns, `chat` for typed/quick-reply turns) within the same conversation |
| 4 | Coach reply also spoken aloud | ✅ confirmed via TextToSpeech engine binding live + scenario 5's interrupt proving playback was active |
| 5 | Push-to-talk mid-playback stops audio immediately | ✅ live — user confirmed audio stopped instantly with no lingering/overlap when mic was pressed during a reply |
| 6 | Disable "Spoken replies" in Settings; persists across restart | ✅ live — toggled off, force-stopped + relaunched app, `Settings` still showed it unchecked after re-fetch; re-enabled after |
| 7 | Deny mic permission → disabled state, chat still works | ✅ live — real OS "Allow Skill Coach to record audio?" dialog, denied, exact guidance copy shown, text message sent successfully |
| 8 | Silent hold, release → discarded gracefully | ✅ live — multiple no-speech timeouts during testing produced zero stray/empty sent messages and no crash |
| 9 | Web (Chrome desktop) push-to-talk | ✅ live Playwright run (not cached) — `voice.spec.ts` 6/6 passed |
| 10 | Web (unsupported browser) degrades cleanly | ✅ live Playwright run — same suite, unsupported-browser case passed |
| 11 | Independent STT/TTS degrade (no on-device voice for language) | ✅ covered by `voice-capabilities.test.ts`'s dedicated independence tests (exact scenario, mocked expo-speech); not additionally reproduced with a real missing device voice pack |
| 12 | Rapid re-press of push-to-talk | ✅ live — two presses ~1s apart produced one clean recognition cycle each, no crash, no garbled state, app returned to idle |

Language sampling (Constitution VIII): scenarios above ran in English
live. Hindi/Spanish/French/German smoke coverage is exercised by the
existing automated suites (jest/pytest locale parametrization,
`docs/testing.md`), not independently re-spoken live this session.

**Bugs found and fixed during this run:**
1. **Maestro flow race**: `extendedWaitUntil: visible: "Skill Coach"` after
   sign-in was satisfied prematurely because "Skill Coach" is also the
   app-name branding shown on the sign-in screen itself, causing a false
   "Add skill not found" failure. Fixed in `voice-push-to-talk.yaml` and
   `voice-permission-denied.yaml` to wait on "Add skill" instead (unique to
   the post-auth skills list).
2. **`voice-permission-denied.yaml` never actually tested denial**: Maestro
   auto-grants Android runtime permissions by default, silently defeating
   the flow's "tap Don't Allow" step on every real run. Fixed by pre-denying
   via `launchApp: permissions: microphone: deny`.

Both fixes are live-verified, not just theoretical — T032 passed end-to-end
after applying them. The `maestro test` CLI itself remained flaky on this
specific device (gRPC `DEADLINE_EXCEEDED` after ~120s on `viewHierarchy`/
`deviceInfo` calls, a wireless-ADB/old-hardware driver characteristic
already documented under T011) — final confirmation for T011/T021/T032 was
done by driving the same flows via direct `adb`/hierarchy inspection rather
than a clean `maestro test` exit code, with real speech, a real permission
dialog, and a real user physically present to verify audio behavior no
screenshot or log can prove.
