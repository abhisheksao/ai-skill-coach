# API Contract — 001 Foundations

Base URL: `https://<api-host>` (Render free tier). All `/v1/*` routes require
`Authorization: Bearer <supabase access token>`; the verified JWT `sub` is the
tenant key for every read/write (Constitution I). Content type: JSON.

## Error envelope (all endpoints)

```json
{ "error": { "code": "string", "message_key": "string" } }
```

`message_key` is an i18n catalog key — the client renders it in the profile
language (Constitution X). Codes used in 001: `unauthorized`, `budget_exceeded`,
`llm_unavailable`, `validation_error`, `internal`.

## GET /health

Unauthenticated. Liveness for host health checks and pre-demo warm-up pings.

- **200** `{ "status": "ok", "version": "<git sha>" }`

## POST /v1/profile

Completes the post-signup profile step: upserts the `profiles` row, then
`MERGE`s `(:User)` (FR-006). Idempotent — safe to retry.

Request:

```json
{
  "display_name": "Abhi",        // optional, 1–60 chars when present
  "language": "hi",              // required: en|hi|es|fr|de
  "timezone": "Asia/Kolkata",    // required: IANA name
  "consent": true                 // required: must be true
}
```

Responses:

- **200** `{ "profile": { "display_name", "language", "timezone", "consent_at" } }`
  — returned for both create and repeat calls.
- **422** `validation_error` — bad language code / timezone / `consent != true`.
- **401** `unauthorized`.

Note: if the Neo4j write fails after the profile upsert (e.g. Aura paused), the
endpoint still returns 200; reconciliation happens on the next authenticated
`/chat` call (spec US3 scenario 2). Failure is logged.

## POST /v1/chat

The single message pipeline (Constitution IV). Non-streaming (decision
2026-07-12).

Request:

```json
{
  "message": "hello coach",       // required, 1–4000 chars
  "session_id": "uuid"            // required, client-generated per conversation
}
```

Behavior: verify JWT → `ensure_user` (lazy reconciliation) → budget guard →
LLM structured call → persist both messages (`modality: "chat"`,
`skill_id: null` in 001) → respond. The reply is generated in the profile
language.

Responses:

- **200**

```json
{
  "reply": "Hello! What would you like to work on?",
  "session_id": "uuid",
  "intents": []                   // always empty in 001; envelope fixed for 002
}
```

- **429** `budget_exceeded` — daily counter over limit; client renders
  `message_key` as a coach bubble.
- **503** `llm_unavailable` — provider failed after backoff retries; the user's
  message was **not** persisted (retry sends it again; no phantom duplicates,
  FR-007 / edge case).
- **401** `unauthorized`; **422** `validation_error`.

## Client-direct Supabase access (not via this API)

- **Reads**: `messages` history (`select` own rows, RLS) — conversation reload
  (FR: persistence scenarios); `profiles` own row (drives routing to the
  profile step and the i18n language).
- **Writes**: none. All writes flow through the API (research R9).

## Contract tests (pytest, CI)

1. `/health` 200 without auth.
2. `/v1/*` → 401 with missing/expired/garbage token.
3. `/v1/profile` create → 200, `profiles` row + `(:User)` exist (Neo4j mocked or
   test instance); repeat call → 200, still exactly one of each.
4. `/v1/profile` with `consent: false` → 422.
5. `/v1/chat` happy path (LLM mocked) → 200, two `messages` rows with correct
   `user_id`, `session_id`, `modality`, and `intents == []`.
6. `/v1/chat` over budget → 429, no LLM call, no message rows.
7. `/v1/chat` LLM failure after retries → 503, zero message rows.
8. JWT of user A can never read/write rows of user B (scoping test).
