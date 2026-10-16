"""Apply api/migrations/neo4j/*.cypher to the Neo4j instance in api/.env.

Run from api/ (scripts/bootstrap.sh does this for you):

    cd api && uv run python ../scripts/neo4j_init.py

Uses the API's own driver setup (GraphService.from_settings), so TLS works
the same way it does for the running backend. Every statement in the
migration files is idempotent (`IF NOT EXISTS`), so re-running is safe.
"""

import asyncio
import sys
from pathlib import Path

from skillcoach_api.config import get_settings
from skillcoach_api.services.graph import GraphService

MIGRATIONS = Path(__file__).resolve().parent.parent / "api" / "migrations" / "neo4j"


def statements(text: str) -> list[str]:
    lines = [line for line in text.splitlines() if not line.strip().startswith("//")]
    return [stmt.strip() for stmt in "\n".join(lines).split(";") if stmt.strip()]


async def main() -> int:
    graph = GraphService.from_settings(get_settings())
    if graph.driver is None:
        print("NEO4J_URI / NEO4J_PASSWORD are not set in api/.env", file=sys.stderr)
        return 1
    try:
        async with graph.driver.session() as session:
            for path in sorted(MIGRATIONS.glob("*.cypher")):
                for stmt in statements(path.read_text()):
                    await session.run(stmt)
                print(f"applied {path.name}")
    finally:
        await graph.driver.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
