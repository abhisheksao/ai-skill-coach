# Data Model — 002 Wizard & Plan Generation

Phase 1 output. Graph placement per Constitution VII; schema per
constitution v1.5.0 (verbatim, no changes needed — 002 is the first feature
to actually write it).

## Neo4j (Aura Free)

### `(:Skill)`

| Property | Type | Notes |
|---|---|---|
| `id` | string (uuid) | server-generated on `create_skill` |
| `name` | string | from `new_skill_name`, verbatim (research R2) |
| `created_at` | datetime | set on create |

Relationship: `(:User)-[:PURSUES]->(:Skill)` — the authenticated `sub`'s
User node (created in 001) to this Skill.

### `(:Goal)`

| Property | Type | Notes |
|---|---|---|
| `id` | string (uuid) | |
| `statement` | string | e.g. "Swim 1km continuously" |
| `target_date` | date | |
| `created_at` | datetime | |

Relationships: `(:Skill)-[:HAS_GOAL]->(:Goal)`;
`(:Goal)-[:SUPERSEDES]->(:Goal)` on `revise_goal` (Constitution III — old
Goal untouched, never deleted).

### `(:Plan)`

| Property | Type | Notes |
|---|---|---|
| `id` | string (uuid) | |
| `created_at` | datetime | |

Relationships: `(:Skill)-[:HAS_PLAN]->(:Plan)`;
`(:Plan)-[:FOR_GOAL]->(:Goal)` (which goal this plan serves, constitution
v1.4.0); `(:Plan)-[:SUPERSEDES]->(:Plan)` on `revise_plan`/regenerate — one
active (non-superseded) Plan per Skill at all times.

### `(:Step)`

| Property | Type | Notes |
|---|---|---|
| `order` | int | 1-indexed, unique within a Plan |
| `description` | string | |
| `cadence_per_week` | int | 1–14 |

Relationship: `(:Plan)-[:HAS_STEP]->(:Step)`. Bounded to 3–12 Steps per Plan
(FR-010). No status field — derived from CheckIn in feature 004
(Constitution II); 002 never reads or writes Step status.

## Derived values (no new storage)

- **Regeneration attempt count**: `size((activePlan)-[:SUPERSEDES*0..]->(:Plan)) `
  back to the Plan created by the original `create_plan` for this intake —
  computed at request time in `SkillsService`, never stored (research R5).
- **Wizard turn count**: `COUNT` of `messages` rows for the active
  `session_id` — computed at request time, never stored (research R1).

## Postgres (Supabase) — unchanged tables, new usage

- `messages.skill_id`: nullable column already exists (001). 002 starts
  populating it once a Skill exists for the session; remains `null` for
  messages exchanged before `create_skill` applies.

No new Postgres tables. No changes to `profiles` or `llm_usage`.

## Pydantic Intent Schemas (`api/src/skillcoach_api/models/intents.py`)

```python
class StepPayload(BaseModel):
    description: str = Field(min_length=1, max_length=200)
    order: int = Field(ge=1, le=12)
    cadence_per_week: int = Field(ge=1, le=14)

class CreateSkillIntent(BaseModel):
    type: Literal["create_skill"]
    name: str = Field(min_length=1, max_length=80)

class CreatePlanIntent(BaseModel):
    type: Literal["create_plan"]
    skill_name: str
    goal_statement: str = Field(min_length=1, max_length=300)
    target_date: date
    weekly_days: int = Field(ge=1, le=7)
    weekly_minutes_per_day: int = Field(ge=5, le=240)
    steps: list[StepPayload] = Field(min_length=3, max_length=12)

class RevisePlanIntent(BaseModel):
    type: Literal["revise_plan"]
    skill_name: str
    steps: list[StepPayload] = Field(min_length=3, max_length=12)

class ReviseGoalIntent(BaseModel):
    type: Literal["revise_goal"]
    skill_name: str
    goal_statement: str = Field(min_length=1, max_length=300)
    target_date: date

Intent = Annotated[
    CreateSkillIntent | CreatePlanIntent | RevisePlanIntent | ReviseGoalIntent,
    Field(discriminator="type"),
]
```

`ChatTurn.intents: list[Intent]` replaces 001's `list[dict]` placeholder
(research R7).

## Invariants

1. `create_skill` and `create_plan` in the same turn apply in **one Neo4j
   transaction** — a Skill is never created without its Goal+Plan, and
   vice versa (FR-004, SC-004).
2. Every write is scoped to the authenticated `sub`'s `(:User)` node —
   `apply_intents` never accepts a user id from the intent payload itself,
   only from the verified JWT (Constitution I).
3. Exactly one non-superseded Plan exists per Skill at all times; exactly
   one non-superseded Goal exists per Skill at all times (constitution
   v1.4.0/v1.5.0 schema invariants, unchanged by this feature).
4. Step order is contiguous 1..N within a Plan (validated at the Pydantic
   layer before any Cypher runs).
