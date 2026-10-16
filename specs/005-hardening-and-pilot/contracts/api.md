# API Contract Changes: Hardening & Pilot (005)

**Date**: 2026-07-18 | **Plan**: [../plan.md](../plan.md)

005 adds **no new public endpoints**. Its externally visible contract
changes are: budget-exhaustion semantics on chat, an enriched error
envelope, and formalized guarantees on every existing endpoint. Operator
surfaces (SQL views, scripts, workflows) are internal and documented in
`docs/runbooks/`, not here.

## Changed: `POST /v1/chat` — budget exhaustion is a 200 turn

**Before (001–004)**: daily budget exceeded → `429`
`{"error": {"code": "budget_exceeded", "message_key": "errors.budget_exceeded"}}`.

**After (005, research.md R2)**: the same condition returns **200** with
an ordinary chat-turn body:

```json
{
  "reply": "errors.budget_exhausted_reply",
  "intents_applied": [],
  "budget": {"exhausted": true, "resets_at": "2026-07-19T00:00:00Z"}
}
```

- `reply` carries an i18n key (client renders it in the profile
  language, Constitution X), exactly like the existing degraded-
  validation turn's `errors.validation`.
- `resets_at` is the UTC start of the next budget day (the `usage_date`
  boundary `llm_usage` already uses).
- Zero LLM calls are made; the turn is persisted the same way the
  degraded turn is, so the transcript reflects what the user saw.
- The `budget` object is absent on normal turns (additive, backward
  compatible).

**Provider-outage behavior is unchanged** in shape (503
`llm_unavailable` after retries exhaust) but the queue makes it rarer;
SC-002 requires the client render for it to remain friendly, never raw.

## Changed: error envelope for `budget_exceeded` (non-chat callers)

Any endpoint that still surfaces `BudgetExceeded` as an error (e.g.
internal session-summarize skipping a user) returns the existing
envelope **plus** `resets_at`:

```json
{"error": {"code": "budget_exceeded", "message_key": "errors.budget_exceeded", "resets_at": "2026-07-19T00:00:00Z"}}
```

Additive; existing clients that ignore the field are unaffected.

## New guarantee: blocked users (kill switch)

When `user_limits.blocked = true`, LLM-consuming requests behave exactly
as budget-exhausted (same 200 turn on chat, same envelope elsewhere,
`resets_at` omitted — there is no automatic reset). Deliberately
indistinguishable from exhaustion to the client: no new client states,
nothing user-hostile to render, and unblocking is an operator action.

## Formalized (no shape change): logging & analytics side effects

- Every request continues to emit the one-line JSON request log
  (`request_id`, `method`, `path`, `status`, `duration_ms`, `sub`);
  005 adds the policy guarantee — **no transcript bodies, tokens, or
  secrets, ever** (FR-007, redaction-tested) — and a structured
  `ai_failure` event (endpoint, sub, intent type, failure class) on LLM
  validation/provider failures.
- Chat, session-summarize, and push paths additionally write
  `analytics_events` rows per the vocabulary in
  [data-model.md](../data-model.md); fire-and-forget — never affects
  response codes or latency contracts.

## Unchanged

All other endpoints (`/v1/skills`, `/v1/intents/apply`, `/v1/dashboard`,
`/v1/skills/{id}/progress`, `/v1/push-tokens`, `/v1/internal/*`,
`/health`) keep their 001–004 contracts. `/health` remains the probe
target for the new `healthcheck.yml` workflow — its existing 200 +
`git_sha` body is sufficient; no change.

## Client-facing configuration (not HTTP, but contract-adjacent)

- `EXPO_PUBLIC_DELETE_ACCOUNT_URL` — URL opened by the Settings
  "Delete account" row (R13); placeholder now, static policy page later,
  swap requires no build logic change (spec edge-case resolution).
- Sign in with Apple joins Google in the auth screen; both flow through
  the same Supabase auth session — the backend sees identical JWTs and
  needs no change (R11).
