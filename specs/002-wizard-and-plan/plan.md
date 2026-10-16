# Implementation Plan: Wizard & Plan Generation

**Branch**: `002-wizard-and-plan` | **Date**: 2026-07-14 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/002-wizard-and-plan/spec.md`

## Summary

A signed-in user picks or names a skill, is guided through a four-topic intake
(level, target, timeline, weekly time) by the coach, confirms it, and receives
a generated plan (Goal + ordered Steps) written atomically to Neo4j. The
review screen lets them accept (no-op — the plan is already recorded) or
regenerate with a required reason (too much / too easy / not quite right),
capped at 3 visible attempts with a similarity-guarded internal retry. This
plan extends 001's `/v1/chat` pipeline with real intents (`create_skill`,
`create_plan`, `revise_plan`, `revise_goal`) instead of the always-empty list
001 shipped, adds a skills list/detail API, and adds a dedicated regenerate
endpoint since regeneration has its own attempt-counting and similarity-check
logic that doesn't belong in generic chat.

## Technical Context

**Language/Version**: unchanged from 001 — TypeScript/Expo (app), Python 3.12
(api).

**Primary Dependencies**: unchanged (LangChain, neo4j driver, FastAPI,
Pydantic). No new dependency: the materially-similar-plan detector uses
`difflib.SequenceMatcher` from the Python standard library.

**Storage**: Neo4j gains real writes for `(:Skill)`, `(:Goal)`, `(:Plan)`,
`(:Step)` per the constitution's v1 schema — 002 is the first feature to
write them. Postgres `messages.skill_id` (nullable since 001) starts getting
populated; no new Postgres tables.

**Testing**: pytest for the intent→Cypher translator (one test per intent,
plus atomicity and validation-failure/retry paths, per FR-009) and the
context builder; jest/tsc for the new app screens.

**Target Platform**: unchanged (iOS/Android/web from one Expo codebase).

**Project Type**: unchanged monorepo (`app/` + `api/`).

**Performance Goals**: none new; wizard turns and regeneration reuse 001's
non-streaming `/v1/chat` latency profile.

**Constraints**: plan bounded to 3–12 steps; wizard force-summarizes at 12
turns; regeneration capped at 3 user-visible attempts + ≤1 internal
similarity retry; all writes atomic per intake completion (FR-004).

**Scale/Scope**: ~4 intents, 1 new route file (`skills.py`) with 3 endpoints,
2 new services (`intent_apply.py`, `context_builder.py`) plus a small
similarity helper, 1 extended service (`llm.py` gains a plan-turn method), 3
new app screens (skill list, wizard chat, plan review).

## Constitution Check

*GATE: evaluated against constitution v1.5.0 — re-checked after Phase 1.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | LLM never writes Cypher; intents may be LLM- or UI-native | PASS | Four LLM-produced intents this feature; the `apply_intents` translator is written as `(intents, user_id) -> None` independent of origin, so it's directly reusable by 004's UI-native taps later — no rework needed then. |
| II | Progress derived | PASS (N/A writes) | Step carries no status field; 002 doesn't touch CheckIn at all. |
| III | Goal immutable; no UI delete | PASS | `create_plan` writes the first Goal; `revise_goal`/`revise_plan` always create superseding nodes, never overwrite. No delete affordance anywhere in this feature. |
| IV | Single message pipeline | PASS | Still one `/v1/chat` endpoint; `modality` stays `chat`; `skill_id` now populated instead of always-null. |
| V | Budgeted LLM calls | PASS, flagged | v0 guard unchanged. **Deviation flagged**: Constitution V says generation/coaching turns should use the standard model tier, but 002 continues on `gemini-3.1-flash-lite` (500 RPD) rather than switching to standard-tier Flash (measured at 20 RPD in AI Studio, 2026-07-13) — a multi-turn wizard plus up to 3 regenerations would exhaust a 20 RPD budget in one or two test sessions. This is a deliberate, config-only, revisit-at-005 pragmatic call (Constitution VI), not a silent gap — recorded here and in research.md. |
| VI | Provider/tier config-only | PASS | Same `LLM_MODEL` env var; no code branches on model identity. |
| VII | Data placement | PASS | Skill/Goal/Plan/Step in Neo4j; intake facts never persisted server-side in any store (FR-004) — reconstructed from conversation history each turn, never written as a draft row. |
| VIII | Testing | PASS | FR-009's unit-test requirement covers the translator and context builder; EN+HI full, ES/FR/DE smoke per Principle VIII. |
| IX | Cost ceiling | PASS | Still $0/mo; no new services. |
| X | Multilingual | PASS | Wizard and plan content generated in profile language (spec assumption), reusing 001's language plumbing unchanged. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-wizard-and-plan/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md           # Phase 1 output
└── tasks.md              # Phase 2 (/speckit-tasks — not yet created)
```

### Source Code (repository root)

```text
api/src/skillcoach_api/
├── models/
│   ├── chat.py           # EXTEND: ChatTurn.intents -> discriminated union
│   │                     #   (was list[dict] placeholder in 001);
│   │                     #   ChatRequest gains skill_id, new_skill_name
│   ├── intents.py        # NEW: CreateSkillIntent, CreatePlanIntent
│   │                     #   (nests GoalPayload + list[StepPayload]),
│   │                     #   RevisePlanIntent, ReviseGoalIntent
│   └── skills.py         # NEW: SkillSummary (list), SkillDetail (goal+
│                         #   plan+steps+generation number)
├── services/
│   ├── llm.py             # EXTEND: system prompts for wizard turns and
│   │                     #   for the regenerate turn; both reuse the
│   │                     #   existing generate()-shaped call
│   ├── context_builder.py # NEW: assembles profile + (if skill_id) that
│   │                     #   skill's goal/plan/steps + recent session
│   │                     #   messages, for the LLM prompt (FR-008)
│   ├── intent_apply.py    # NEW: apply_intents(intents, user_id) —
│   │                     #   ONE Neo4j transaction per call (atomicity,
│   │                     #   FR-004); one Cypher builder per intent type
│   ├── plan_similarity.py # NEW: stdlib difflib-based "materially
│   │                     #   similar" check between two step lists
│   └── skills.py          # NEW: SkillsService — list_skills, get_skill,
│                         #   regeneration-count-so-far (via SUPERSEDES
│                         #   chain depth on the active Plan)
├── routes/
│   ├── chat.py             # EXTEND: pass skill_id/new_skill_name through
│   │                     #   to context builder; apply real intents via
│   │                     #   intent_apply instead of the 001 no-op
│   └── skills.py          # NEW: GET /v1/skills, GET /v1/skills/{id},
│                         #   POST /v1/skills/{id}/plan/regenerate
└── tests/
    ├── test_intents.py            # NEW — one test per intent type
    ├── test_intent_apply.py       # NEW — atomicity, validation failure
    ├── test_context_builder.py    # NEW
    ├── test_plan_similarity.py    # NEW
    └── test_skills_contract.py    # NEW

app/src/app/(main)/
├── skills.tsx             # NEW: skill cards (User Story 3) + "add skill"
│                         #   entry (name input + client-side duplicate
│                         #   check against GET /v1/skills, FR-012)
├── wizard.tsx             # NEW: reuses chat.tsx's bubble/send components,
│                         #   parameterized by skill_id (null while in
│                         #   the wizard, set once create_skill applies)
└── plan-review.tsx        # NEW: goal + ordered steps, Accept (dismiss —
                          #   no API call, plan is already persisted) and
                          #   Regenerate (reason picker -> POST regenerate)
```

**Structure Decision**: Same monorepo; no new top-level directories. All
002 additions are new files inside the existing `api/src/skillcoach_api/`
and `app/src/app/(main)/` trees established in 001.

## Implementation Notes (how the pieces connect)

1. **Intake has no server-side state, by design (FR-004).** Rather than a
   `wizard_state` table or a new intent type to track draft progress, the
   LLM reconstructs "where are we in the four topics" by reading that
   session's recent messages (already persisted since 001; the context
   builder includes the last ~20 turns for the active `session_id`). Turn
   counting for the 12-turn force-summarize cap (FR-010) is a `COUNT` over
   existing `messages` rows for that session — no new storage.
2. **Starting a wizard**: client collects the skill name via a plain text
   field (not conversationally) and does the duplicate-name check
   client-side against `GET /v1/skills` (fuzzy, case-insensitive) — no LLM
   call spent on FR-012. The first `/v1/chat` call for a new skill sends
   `skill_id: null, new_skill_name: "Swimming"`; the server holds that name
   verbatim for when `create_skill` is eventually applied, rather than
   trusting the LLM to spell it back correctly.
3. **Atomic completion (FR-004)**: when the LLM's turn includes both
   `create_skill` and `create_plan` (wizard finished), `apply_intents` runs
   both Cypher writes in a **single Neo4j transaction** — partial writes are
   impossible, satisfying SC-004. The client recognizes wizard completion by
   the response's `skill_id` becoming non-null and routes to the plan review
   screen, reading the now-persisted plan via `GET /v1/skills/{id}` (FR-007:
   review renders recorded state, not raw LLM output).
4. **Accept is a no-op API-wise.** Because the plan is written the moment
   intake is confirmed (not deferred until "accept"), the Accept button just
   navigates away — nothing left to write.
5. **Regenerate is its own endpoint**, not a chat message, because it needs
   structured attempt-count enforcement: `POST /v1/skills/{id}/plan/regenerate`
   with `{reason, note?}`. The attempt count is *derived*, not stored —
   it's the length of the active Plan's `SUPERSEDES` chain since the
   original `create_plan` (consistent with Constitution II's "derive, don't
   store" spirit). At 3, the endpoint returns 409 `regeneration_cap_reached`
   instead of calling the LLM; the client then routes into an ordinary
   wizard conversation to revise the goal/timeline (reusing `revise_goal`/
   `revise_plan` — no new intents needed for the "back to wizard" path).
6. **Regenerate still talks like a coach.** It reuses the same
   `{reply, intents: [revise_plan]}` structured-call shape as any chat turn
   (system prompt swapped for a regeneration-specific one carrying the
   reason/note/current plan), so the user gets a short coach reply
   ("Here's a lighter version!") alongside the new plan, not a bare API
   response.
7. **Similarity guard**: before applying a regenerated plan, compare its
   step descriptions to the plan being replaced via
   `difflib.SequenceMatcher` (order-insensitive, normalized text). Above a
   fixed similarity threshold, re-invoke the LLM once with an explicit
   "produce a meaningfully different approach" instruction before applying
   anything — this retry never touches the user-visible attempt count.

## Complexity Tracking

No constitution violations — table intentionally empty.
