# API Contract — 002 Wizard & Plan Generation

Extends `specs/001-foundations/contracts/api.md`. Same auth (Bearer JWT),
same error envelope (`{error: {code, message_key}}`).

## POST /v1/chat (extended)

Request gains two fields; response gains one.

```json
{
  "message": "I want to get better at swimming",
  "session_id": "uuid",
  "skill_id": null,
  "new_skill_name": "Swimming"
}
```

- `skill_id`: `uuid | null`. Null while in a brand-new wizard (before
  `create_skill` has applied); set for all conversation within an existing
  skill.
- `new_skill_name`: present only on the first call of a new wizard;
  authoritative for the eventual `create_skill` intent (research R2). Absent
  when `skill_id` is set.

Response:

```json
{
  "reply": "Nice! Have you swum before, or starting from scratch?",
  "session_id": "uuid",
  "skill_id": null,
  "intents": []
}
```

`skill_id` in the response becomes non-null the turn `create_skill` applies
— the client's signal to route to the plan review screen (implementation
note 3). `intents` echoes what was applied this turn (empty on ordinary
wizard turns; `["create_skill", "create_plan"]`-shaped once, at completion).

Behavior addition: before generating a reply, the server assembles context
via `context_builder` (profile +, if `skill_id` set, that skill's
goal/plan/steps + last ~20 session messages) and counts prior user messages
in the session to enforce the 12-turn force-summarize (FR-010). If the
turn's intents include `create_skill`+`create_plan` or `revise_goal`/
`revise_plan`, they're validated and applied atomically via
`intent_apply.apply_intents` before the response is returned; validation
failure retries the whole LLM call (max 2, Constitution I), then degrades
to a reply-only turn with the failure logged (FR-006).

## GET /v1/skills

List the caller's skills as cards (User Story 3).

- **200**

```json
{
  "skills": [
    {
      "id": "uuid",
      "name": "Swimming",
      "created_at": "2026-07-14T09:00:00Z",
      "goal_statement": "Swim 1km continuously",
      "target_date": "2026-12-01",
      "step_count": 6
    }
  ]
}
```

Used client-side for the duplicate-name check (FR-012, research R2/R9) —
no server-side duplicate endpoint.

## GET /v1/skills/{skill_id}

Full detail for the plan review screen and ongoing skill conversations.

- **200**

```json
{
  "id": "uuid",
  "name": "Swimming",
  "goal": { "statement": "Swim 1km continuously", "target_date": "2026-12-01" },
  "plan": {
    "id": "uuid",
    "generation": 0,
    "steps": [
      { "order": 1, "description": "Float and glide drills", "cadence_per_week": 3 }
    ]
  }
}
```

`generation` is the derived regeneration count (research R5) — `0` for the
originally generated plan, incrementing per accepted regeneration.

- **404**: skill doesn't exist or doesn't belong to the caller (never
  distinguishes the two — Constitution I tenant scoping).

## POST /v1/skills/{skill_id}/plan/regenerate

```json
{ "reason": "too_much", "note": "the swim distances jump too fast" }
```

`reason` ∈ `too_much | too_easy | not_quite_right` (required); `note`
optional, ≤200 chars.

Behavior: loads current Goal+Plan+Steps via context builder, calls the LLM
with a regeneration-specific system prompt carrying reason/note/current
plan (same `{reply, intents: [revise_plan]}` shape as chat, research R4).
Before applying, compares the new steps to the current plan's steps via
`plan_similarity` (research R6); if materially similar, re-prompts the LLM
once (transparent, uncounted) before proceeding. Applies `revise_plan`
(supersedes the current Plan, same `FOR_GOAL`) in one transaction.

- **200**

```json
{
  "reply": "Here's a gentler ramp-up for you.",
  "plan": { "id": "uuid", "generation": 1, "steps": [ /* ... */ ] }
}
```

- **409** `regeneration_cap_reached` — the derived attempt count is already
  3; no LLM call is made. `message_key` guides the client to open a wizard
  conversation on this skill to revise the goal/timeline instead.
- **404**: skill not found / not owned by caller.
- **429/503**: budget/LLM failure, same envelope as `/v1/chat`.

## Contract tests (pytest, added to CI-equivalent local run)

1. `create_skill` alone (no `create_plan` in the same turn) never commits —
   atomicity test asserts partial-write impossibility.
2. `create_skill` + `create_plan` together commit as one transaction;
   killing the transaction mid-way (simulated) leaves neither node.
3. Each intent type: valid payload applies correctly; invalid payload
   (e.g., 2-step plan, violates `min_length=3`) triggers the retry path,
   then graceful degradation, never a partial write.
4. `GET /v1/skills` returns only the caller's own skills (tenant scoping,
   extends 001's contract test 8 pattern).
5. `POST .../plan/regenerate` at generation 3 returns 409 without an LLM
   call (assert zero calls to the LLM fake).
6. Two step lists that are reworded-but-substantively-identical trigger
   exactly one internal re-prompt (`plan_similarity` returns "similar",
   LLM fake called twice, user-visible attempt count unaffected).
7. Regeneration reason/note appear in the system prompt passed to the LLM
   fake (asserts the context actually carries them, per FR-011).
