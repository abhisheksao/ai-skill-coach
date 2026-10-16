# Data Model — Voice Layer

No Neo4j graph changes — voice is a message-ingestion-layer and
client-preference feature only; nothing here touches Skill/Goal/Plan/Step.

## Postgres: `messages` (extended, no migration needed)

`messages.modality` already exists (001's initial migration) with
`check (modality in ('chat', 'voice'))`. 003 is the first feature to
actually store `'voice'` — no schema change, only application code
(`MessageStore.insert_turn` currently hardcodes `'chat'`, see
research.md R6).

| Column | Type | Notes |
|---|---|---|
| `modality` | `text` | Unchanged constraint; `'voice'` becomes reachable for the first time. |

Per FR-005/Constitution IV: a voice-originated `messages` row is
byte-for-byte identical to a chat row except this column — `content`
holds the user-confirmed (possibly hand-edited) final transcript, never
raw recognizer output, and never the interim/discarded partials.

## Postgres: `profiles` (extended — new migration)

New column, additive and backward-compatible (defaults to `true` so
existing rows need no backfill):

```sql
alter table public.profiles
    add column voice_replies_enabled boolean not null default true;
```

| Column | Type | Notes |
|---|---|---|
| `voice_replies_enabled` | `boolean not null default true` | Per-user persisted setting (FR-004, US2 scenario 3); read-only to the client under RLS like every other profile column — writes go through `POST /v1/profile` (service role) only. |

No new table — this is a single additive column on the table 001 already
created, following the same RLS posture (`profiles_select_own`; no
client insert/update/delete policies) as every existing profile field.

## Client-side (transient, not persisted anywhere)

These exist only in `use-voice-session`'s in-memory state — never written
to Postgres, Neo4j, or AsyncStorage, per FR-007/Constitution VII ("the
raw audio is not retained; only transcripts persist"):

- **Recording state**: `idle | recording | listening-no-interim |
  editable-final`. Drives which of {nothing, live interim text,
  "Listening…" indicator, editable transcript box} `ConversationView`
  renders (research.md R2, clarified FR-002).
- **Confidence gate**: `needsConfirmation: boolean`, set only when the
  platform reported a confidence score below 0.5 (clarified FR-003);
  `undefined`/unset when no score was reported at all — distinct from
  `false`, since the UI treats "no signal" and "high confidence" the
  same way (no extra prompt) but for different reasons worth keeping
  distinguishable for future debugging/telemetry.
- **Capability cache**: `{ stt: boolean, tts: boolean }` per language,
  recomputed on profile-language change (research.md R7/`voice-
  capabilities.ts`) — never persisted; cheap enough to recompute per app
  session.
