# API Contract — 004 Progress Loop & Notifications

Extends `specs/003-voice-layer/contracts/api.md`. Same auth (Bearer JWT
via `RequirePrincipal`), same error envelope
(`{error: {code, message_key}}`), except the two internal endpoints,
which use a shared-secret header instead of a user JWT (research.md R1).

## POST /v1/chat (extended — new intent types only, no shape change)

`ChatResponse.intents` can now additionally contain `log_checkin`,
`report_obstacle`, or `complete_step` entries (joining the existing
`create_skill`/`create_plan`/`revise_plan`/`revise_goal`) — the request/
response shape is unchanged; only the `Intent` union recognized and
applied grows. See `data-model.md` for the three new intent field shapes.

## POST /v1/intents/apply (new — UI-native tap path)

No LLM call in this path (SC-007). Request:

```json
{
  "skill_id": "uuid",
  "intent": {
    "type": "complete_step",
    "step_order": 3,
    "sentiment": "positive"
  }
}
```

- `intent`: discriminated on `type`, one of `complete_step` |
  `log_checkin` only (not `report_obstacle` — obstacles need a coach
  response, conversation-only per User Story 1/7 split, research.md R6).
- `source` is never a request field — the server always writes
  `source: "ui_tap"` for anything applied through this route (FR-016).

Response:

```json
{
  "checkin_id": "uuid",
  "applied_at": "2026-07-20T10:00:00Z"
}
```

On validation failure: standard error envelope, HTTP 400, no retry (FR-015
— "no LLM retry path applies to this case"). On success, no partial write
is possible — the same single-transaction `IntentApplyService` used by
`/v1/chat` (Constitution I).

## GET /v1/skills/{skill_id}/progress (new)

```json
{
  "skill_id": "uuid",
  "completed_steps": [1, 2],
  "total_steps": 6,
  "streak_days": 4,
  "steps": [
    {"order": 1, "completed": true, "behind_cadence": false, "last_checkin_at": "2026-07-19T18:00:00Z"},
    {"order": 2, "completed": false, "behind_cadence": true, "last_checkin_at": "2026-07-10T18:00:00Z"}
  ]
}
```

Every value is computed on demand from `CheckIn` records at request time
(FR-004/Constitution II) — never a cached counter; two requests
immediately after each other, or from different platforms, always agree
(User Story 2 scenario 2).

## GET /v1/dashboard (new)

```json
{
  "skills": [
    {
      "skill_id": "uuid",
      "name": "Swimming",
      "goal_statement": "Swim a 5k open water race",
      "target_date": "2026-10-01",
      "is_stale": false,
      "progress": {
        "completed_steps": 2,
        "total_steps": 6,
        "streak_days": 4
      },
      "steps": [
        {"order": 1, "description": "Float and glide", "completed": true, "behind_cadence": false},
        {"order": 2, "description": "Kick drills", "completed": false, "behind_cadence": true}
      ]
    }
  ]
}
```

`is_stale`: `true` when no `CheckIn` exists anywhere under that skill
within `constants.STALE_GOAL_DAYS` (FR-014). `progress` is the exact same
derivation `GET /v1/skills/{id}/progress` returns, at coarser summary
grain — SC-006 requires these to always agree since both come from the
one `ProgressService`. `steps` (added during Phase 8/User Story 7
implementation, not in the original plan) gives the client enough to
render a tap-to-complete/log-partial affordance per step directly on the
card, without a second round trip per skill. Zero-skills case:
`{"skills": []}` — the client renders the empty state (FR-014 scenario
2).

## POST /v1/push-tokens (new)

```json
{"token": "ExponentPushToken[...]", "platform": "ios"}
```

Upserts on `(user_id, token)` — safe to call again with the same token on
every app foreground (covers rotation without a separate "refresh"
endpoint). Response: `204 No Content`.

## DELETE /v1/push-tokens (new)

Body: `{"token": "ExponentPushToken[...]"}`. Marks that token
`revoked_at = now()` for the calling user (sign-out, FR-013). Response:
`204 No Content`. Idempotent — deleting an already-revoked or unknown
token is not an error.

## POST /v1/internal/notifications/scan (new, internal)

Header: `X-Internal-Secret: <settings.internal_secret>` — 401 (same error
envelope) if missing/wrong. No user JWT; this is a system-to-system call
from `pg_cron`/`pg_net` (research.md R1), never reachable from the app.

Body: none. Response: `{"scanned": 42, "notified": 3, "skipped": 39}` —
summary counts for logging/observability, not consumed by any client.

## POST /v1/internal/sessions/summarize (new, internal)

Same auth as above. Body: none. Response:
`{"sessions_summarized": 5}`.

## Client-only surface (no backend contract)

Push notification permission prompts, the OS notification tray entry, and
`skillcoach://skill/{id}/session` deep-link routing (already-reserved
scheme, `app.json:8`) happen entirely client-side via `expo-notifications`
+ `expo-router`. The deep link's target screen (`chat.tsx` for that
`skill_id`) then calls the existing `/v1/chat` pipeline exactly as an
in-app navigation would — the coach's gap-aware opening comes from
`ContextBuilder` now including cadence-gap + recent-session-summary data
in its context build (see plan.md Implementation Notes), not from
anything the deep link itself carries.
