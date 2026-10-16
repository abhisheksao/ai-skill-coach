"""Read queries over the coaching graph for skill list/detail (FR-001,
User Story 3). All queries scoped to the authenticated user_id
(Constitution I); "active" Goal/Plan means not yet superseded.
"""

from skillcoach_api.models.skills import (
    GoalDetail,
    PlanDetail,
    SkillDetail,
    SkillSummary,
    StepDetail,
)

_LIST_SKILLS = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill)
MATCH (s)-[:HAS_GOAL]->(g:Goal) WHERE NOT (g)<-[:SUPERSEDES]-(:Goal)
MATCH (s)-[:HAS_PLAN]->(p:Plan) WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
MATCH (p)-[:HAS_STEP]->(st:Step)
WITH s, g, count(st) AS step_count
RETURN s.id AS id, s.name AS name, s.created_at AS created_at,
       g.statement AS goal_statement, g.target_date AS target_date,
       step_count
ORDER BY s.created_at ASC
"""

_RECENT_SESSION_SUMMARIES = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_SESSION]->(sess:Session)
RETURN sess.summary AS summary, sess.ended_at AS ended_at
ORDER BY sess.ended_at DESC
LIMIT $limit
"""

_GOAL_HISTORY = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_GOAL]->(current:Goal) WHERE NOT (current)<-[:SUPERSEDES]-(:Goal)
MATCH (current)-[:SUPERSEDES*0..]->(g:Goal)
RETURN DISTINCT g.statement AS statement, g.target_date AS target_date, g.created_at AS created_at
ORDER BY g.created_at ASC
"""

_GET_SKILL = """
MATCH (u:User {id: $user_id})-[:PURSUES]->(s:Skill {id: $skill_id})
MATCH (s)-[:HAS_GOAL]->(g:Goal) WHERE NOT (g)<-[:SUPERSEDES]-(:Goal)
MATCH (s)-[:HAS_PLAN]->(p:Plan) WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
OPTIONAL MATCH path = (p)-[:SUPERSEDES*0..]->(:Plan)
WITH s, g, p, max(length(path)) AS generation
MATCH (p)-[:HAS_STEP]->(st:Step)
WITH s, g, p, generation, st ORDER BY st.order ASC
RETURN s.id AS id, s.name AS name,
       g.statement AS goal_statement, g.target_date AS target_date,
       p.id AS plan_id, generation,
       collect({order: st.order, description: st.description,
                cadence_per_week: st.cadence_per_week}) AS steps
"""


def _native(value):
    """Neo4j temporal types expose .to_native(); plain values pass through."""
    return value.to_native() if hasattr(value, "to_native") else value


class SkillsService:
    def __init__(self, driver) -> None:
        self._driver = driver

    async def list_skills(self, user_id: str) -> list[SkillSummary]:
        async with self._driver.session() as session:
            result = await session.run(_LIST_SKILLS, user_id=user_id)
            records = [record async for record in result]

        return [
            SkillSummary(
                id=r["id"],
                name=r["name"],
                created_at=_native(r["created_at"]),
                goal_statement=r["goal_statement"],
                target_date=_native(r["target_date"]),
                step_count=r["step_count"],
            )
            for r in records
        ]

    async def get_skill(self, user_id: str, skill_id: str) -> SkillDetail | None:
        async with self._driver.session() as session:
            result = await session.run(_GET_SKILL, user_id=user_id, skill_id=skill_id)
            record = await result.single()

        if record is None:
            return None

        return SkillDetail(
            id=record["id"],
            name=record["name"],
            goal=GoalDetail(
                statement=record["goal_statement"], target_date=_native(record["target_date"])
            ),
            plan=PlanDetail(
                id=record["plan_id"],
                generation=record["generation"],
                steps=[StepDetail(**s) for s in record["steps"]],
            ),
        )

    async def recent_session_summaries(self, user_id: str, skill_id: str, limit: int) -> list[str]:
        """Most-recent-first (004, FR-007) — ContextBuilder folds these
        into the coaching prompt for cross-session continuity (SC-003)."""
        async with self._driver.session() as session:
            result = await session.run(
                _RECENT_SESSION_SUMMARIES, user_id=user_id, skill_id=skill_id, limit=limit
            )
            records = [record async for record in result]
        return [r["summary"] for r in records]

    async def goal_revision_history(self, user_id: str, skill_id: str) -> list[GoalDetail]:
        """Every Goal in the skill's SUPERSEDES chain, oldest-first (004,
        FR-011/SC-005) — the current active goal is always the LAST
        entry. Walks forward from the active Goal through zero or more
        SUPERSEDES edges (which point new -> old), so this returns the
        current goal plus every ancestor it superseded, in one query."""
        async with self._driver.session() as session:
            result = await session.run(_GOAL_HISTORY, user_id=user_id, skill_id=skill_id)
            records = [record async for record in result]
        return [
            GoalDetail(statement=r["statement"], target_date=_native(r["target_date"]))
            for r in records
        ]
