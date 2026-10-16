"""Intent -> Cypher translator (Constitution I; data-model.md invariants).

`apply_intents` is the ONLY path from a validated intent to a graph write,
regardless of whether the intent came from an LLM turn or (in feature 004)
a UI-native action. All intents in one call commit as ONE Neo4j managed
transaction (`session.execute_write`) — a create_skill without its
create_plan, or vice versa, is impossible (FR-004, SC-004). Every query is
parameterized and scoped to the authenticated user_id; intents never carry
their own user identity.

Every mutating MATCH targets a skill by **id**, never by name (fixed
2026-07-14, Phase 4/T020): FR-012 explicitly allows two skills to share a
name (the duplicate-name warning can be dismissed), so name-based matching
could silently target the wrong skill once that happens — a real
cross-skill isolation bug, not a hypothetical one. The caller always
already knows which skill it's operating on (chat.py has `body.skill_id`
for an ongoing conversation; the regenerate route has the `skill_id` path
param) — `apply_intents` takes that id explicitly rather than trusting the
LLM to have echoed a unique name back correctly. `create_plan` is the one
exception: it always immediately follows `create_skill` in the same batch
(the atomic wizard-completion write), so it uses the id just generated for
that skill, not a separately supplied one.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from skillcoach_api.models.intents import (
    CompleteStepIntent,
    CreatePlanIntent,
    CreateSkillIntent,
    Intent,
    LogCheckinIntent,
    ReportObstacleIntent,
    ReviseGoalIntent,
    RevisePlanIntent,
)

_CREATE_SKILL = """
MATCH (u:User {id: $user_id})
CREATE (s:Skill {id: $skill_id, name: $name, created_at: datetime()})
CREATE (u)-[:PURSUES]->(s)
"""

_CREATE_PLAN = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
CREATE (g:Goal {
  id: $goal_id, statement: $goal_statement, target_date: date($target_date),
  created_at: datetime()
})
CREATE (s)-[:HAS_GOAL]->(g)
CREATE (p:Plan {id: $plan_id, created_at: datetime()})
CREATE (s)-[:HAS_PLAN]->(p)
CREATE (p)-[:FOR_GOAL]->(g)
WITH p
UNWIND $steps AS step
CREATE (st:Step {
  order: step.order, description: step.description,
  cadence_per_week: step.cadence_per_week
})
CREATE (p)-[:HAS_STEP]->(st)
"""

_REVISE_PLAN = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_PLAN]->(old:Plan)
WHERE NOT (old)<-[:SUPERSEDES]-(:Plan)
MATCH (s)-[:HAS_GOAL]->(g:Goal)
WHERE NOT (g)<-[:SUPERSEDES]-(:Goal)
CREATE (new:Plan {id: $plan_id, created_at: datetime()})
CREATE (s)-[:HAS_PLAN]->(new)
CREATE (new)-[:FOR_GOAL]->(g)
CREATE (new)-[:SUPERSEDES]->(old)
WITH new
UNWIND $steps AS step
CREATE (st:Step {
  order: step.order, description: step.description,
  cadence_per_week: step.cadence_per_week
})
CREATE (new)-[:HAS_STEP]->(st)
"""

_REVISE_GOAL = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_GOAL]->(old:Goal)
WHERE NOT (old)<-[:SUPERSEDES]-(:Goal)
CREATE (new:Goal {
  id: $goal_id, statement: $goal_statement, target_date: date($target_date),
  created_at: datetime()
})
CREATE (s)-[:HAS_GOAL]->(new)
CREATE (new)-[:SUPERSEDES]->(old)
"""

# One shape for all three check-in intents (research.md R5) -- they differ
# only in the `outcome` parameter value, never in query structure. Always
# targets a Step in the skill's ACTIVE (non-superseded) Plan, matched by
# (skill_id, step_order) since Step has no id (002 data-model.md).
_CREATE_CHECKIN = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_PLAN]->(p:Plan) WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
MATCH (p)-[:HAS_STEP]->(st:Step {order: $step_order})
CREATE (c:CheckIn {
  id: $checkin_id, timestamp: datetime($timestamp), created_at: datetime(),
  outcome: $outcome, sentiment: $sentiment, obstacle: $obstacle, source: $source
})
CREATE (c)-[:FOR_STEP]->(st)
"""

_CHECKIN_OUTCOME_BY_TYPE: dict[type, str] = {
    CompleteStepIntent: "completed",
    LogCheckinIntent: "partial",
    ReportObstacleIntent: "obstacle",
}


def _steps_params(intent: CreatePlanIntent | RevisePlanIntent) -> list[dict]:
    return [
        {"order": s.order, "description": s.description, "cadence_per_week": s.cadence_per_week}
        for s in intent.steps
    ]


def _build(
    intent: Intent,
    user_id: str,
    current_skill_id: str | None,
    batch_skill_id: str | None,
    valid_step_orders: set[int] | None,
    source: str,
) -> tuple[str, dict[str, Any]]:
    """`current_skill_id`: caller-supplied, for revise_*/check-in intents on
    an existing skill. `batch_skill_id`: the id generated for a create_skill
    earlier in THIS batch, for the paired create_plan. Exactly one of these
    two is relevant per intent type; the other is ignored.

    `valid_step_orders`: the caller's already-loaded active Plan's step
    orders (chat.py/checkins.py both already have the skill detail before
    calling apply_intents) -- a check-in intent naming a step outside this
    set raises ValueError before any Cypher runs, the same "caller already
    knows the valid context, fail fast in Python" pattern as the
    skill_id-missing checks below, no extra graph round-trip needed."""
    if isinstance(intent, CreateSkillIntent):
        return _CREATE_SKILL, {
            "user_id": user_id,
            "skill_id": str(uuid.uuid4()),
            "name": intent.name,
        }
    if isinstance(intent, CreatePlanIntent):
        if batch_skill_id is None:
            raise ValueError("create_plan requires a create_skill earlier in the same batch")
        return _CREATE_PLAN, {
            "user_id": user_id,
            "skill_id": batch_skill_id,
            "goal_id": str(uuid.uuid4()),
            "goal_statement": intent.goal_statement,
            "target_date": intent.target_date.isoformat(),
            "plan_id": str(uuid.uuid4()),
            "steps": _steps_params(intent),
        }
    if isinstance(intent, RevisePlanIntent):
        if current_skill_id is None:
            raise ValueError("revise_plan requires the caller's current skill_id")
        return _REVISE_PLAN, {
            "user_id": user_id,
            "skill_id": current_skill_id,
            "plan_id": str(uuid.uuid4()),
            "steps": _steps_params(intent),
        }
    if isinstance(intent, ReviseGoalIntent):
        if current_skill_id is None:
            raise ValueError("revise_goal requires the caller's current skill_id")
        return _REVISE_GOAL, {
            "user_id": user_id,
            "skill_id": current_skill_id,
            "goal_id": str(uuid.uuid4()),
            "goal_statement": intent.goal_statement,
            "target_date": intent.target_date.isoformat(),
        }
    if isinstance(intent, LogCheckinIntent | ReportObstacleIntent | CompleteStepIntent):
        if current_skill_id is None:
            raise ValueError(f"{intent.type} requires the caller's current skill_id")
        if valid_step_orders is not None and intent.step_order not in valid_step_orders:
            raise ValueError(
                f"step_order {intent.step_order} not found in skill "
                f"{current_skill_id}'s active plan"
            )
        timestamp = intent.timestamp or datetime.now(UTC)
        return _CREATE_CHECKIN, {
            "user_id": user_id,
            "skill_id": current_skill_id,
            "step_order": intent.step_order,
            "checkin_id": str(uuid.uuid4()),
            "timestamp": timestamp.isoformat(),
            "outcome": _CHECKIN_OUTCOME_BY_TYPE[type(intent)],
            "sentiment": intent.sentiment,
            "obstacle": getattr(intent, "obstacle", None),
            "source": source,
        }
    raise ValueError(f"unknown intent type: {type(intent).__name__}")


@dataclass
class ApplyResult:
    created_skill_id: str | None = None
    checkin_id: str | None = None  # the last check-in intent's generated id, if any (004, T053)


class IntentApplyService:
    def __init__(self, driver) -> None:
        self._driver = driver

    async def apply_intents(
        self,
        intents: list[Intent],
        user_id: str,
        skill_id: str | None = None,
        valid_step_orders: set[int] | None = None,
        source: str = "conversation",
    ) -> ApplyResult:
        """`skill_id`: the conversation's already-resolved skill (None for a
        brand-new wizard, where only create_skill/create_plan are valid).
        `valid_step_orders`: required (non-None) by any caller that might
        apply a check-in intent -- see `_build`'s docstring.
        `source`: `"conversation"` (chat.py) or `"ui_tap"` (checkins.py) --
        one value for the whole batch, never a per-intent/client-supplied
        field (FR-016)."""
        if not intents:
            return ApplyResult()

        # Build once, outside the (possibly retried) transaction function, so
        # generated ids stay deterministic across any driver-level retry.
        batch_skill_id: str | None = None
        checkin_id: str | None = None
        prepared: list[tuple[Intent, tuple[str, dict[str, Any]]]] = []
        for intent in intents:
            built = _build(intent, user_id, skill_id, batch_skill_id, valid_step_orders, source)
            prepared.append((intent, built))
            if isinstance(intent, CreateSkillIntent):
                batch_skill_id = built[1]["skill_id"]
            elif isinstance(intent, LogCheckinIntent | ReportObstacleIntent | CompleteStepIntent):
                checkin_id = built[1]["checkin_id"]

        result = ApplyResult(created_skill_id=batch_skill_id, checkin_id=checkin_id)

        async def _tx(tx):
            for _, (query, params) in prepared:
                await tx.run(query, **params)

        async with self._driver.session() as session:
            await session.execute_write(_tx)

        return result
