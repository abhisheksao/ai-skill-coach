# API Contract — 003 Voice Layer

Extends `specs/002-wizard-and-plan/contracts/api.md`. Same auth (Bearer
JWT), same error envelope (`{error: {code, message_key}}`). No new
endpoints — both changes below are additive fields on existing endpoints.

## POST /v1/chat (extended)

Request gains one field:

```json
{
  "message": "I practiced my breathing drills today",
  "session_id": "uuid",
  "skill_id": "uuid",
  "modality": "voice"
}
```

- `modality`: `"chat" | "voice"`, defaults to `"chat"` when omitted (so
  001/002 client code and tests that never send it keep working
  unchanged). Set to `"voice"` only for a message sent via the
  push-to-talk flow, after the user has confirmed/edited the final
  transcript. Stored verbatim on both the user and assistant `messages`
  rows for that turn (assistant replies inherit the turn's modality,
  same as before — there's still exactly one `modality` per turn, not
  per message row).

Response is unchanged — `modality` is not echoed back; the client already
knows what it sent.

## POST /v1/profile (extended)

Request gains one field:

```json
{
  "display_name": "Jordan",
  "language": "en",
  "timezone": "America/Los_Angeles",
  "consent": true,
  "voice_replies_enabled": false
}
```

- `voice_replies_enabled`: `boolean`, defaults to `true`. Same
  upsert-the-whole-row semantics as `language`/`display_name` (FR-011
  precedent) — settings.tsx always sends the full current value, not a
  partial patch.

Response gains the same field:

```json
{
  "profile": {
    "display_name": "Jordan",
    "language": "en",
    "timezone": "America/Los_Angeles",
    "consent_at": "2026-07-15T00:00:00Z",
    "voice_replies_enabled": false
  }
}
```

## Client-only surface (no backend contract)

Everything else in this feature — starting/stopping the recognizer,
interim transcript events, confidence scores, TTS playback/interrupt,
permission prompts, per-language capability checks — happens entirely
on-device via `expo-speech-recognition` and `expo-speech`. None of it
crosses the API boundary; there is nothing further to contract here.
