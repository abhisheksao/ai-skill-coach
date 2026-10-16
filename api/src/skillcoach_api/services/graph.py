"""Neo4j coaching-graph access (research R10).

`ensure_user` is a parameterized, idempotent MERGE — safe from the profile
step and as the lazy reconciliation on /chat (FR-006). Failures never break
the calling request: Aura Free auto-pauses, and the next call heals.
Constitution I: the only Cypher lives here, parameterized, scoped to the
authenticated sub.
"""

import logging

logger = logging.getLogger(__name__)

_ENSURE_USER = "MERGE (u:User {id: $id}) ON CREATE SET u.created_at = datetime()"


class GraphService:
    def __init__(self, driver=None) -> None:
        self._driver = driver

    @property
    def driver(self):
        """Shared driver, reused by SkillsService/IntentApplyService
        (002) so the app runs one Neo4j connection pool, not several."""
        return self._driver

    @classmethod
    def from_settings(cls, settings) -> "GraphService":
        if not (settings.neo4j_uri and settings.neo4j_password):
            logger.info("Neo4j not configured; graph writes will be skipped")
            return cls(None)
        import certifi
        from neo4j import AsyncGraphDatabase, TrustCustomCAs

        # The +s schemes verify TLS against the system trust store, which is
        # empty on python.org macOS installs (same failure mode as the JWKS
        # fix in auth.py). Use the base scheme with explicit certifi CAs so
        # the driver works on any machine.
        uri = settings.neo4j_uri
        kwargs: dict = {}
        if "+s://" in uri:
            uri = uri.replace("+s://", "://", 1)
            kwargs = {
                "encrypted": True,
                "trusted_certificates": TrustCustomCAs(certifi.where()),
            }

        driver = AsyncGraphDatabase.driver(
            uri, auth=(settings.neo4j_user, settings.neo4j_password), **kwargs
        )
        return cls(driver)

    async def ensure_user(self, sub: str) -> bool:
        """Returns True when the (:User) node is guaranteed to exist."""
        if self._driver is None:
            return False
        try:
            async with self._driver.session() as session:
                await session.run(_ENSURE_USER, id=sub)
            return True
        except Exception as exc:
            logger.warning("ensure_user failed (will heal on next call): %s", type(exc).__name__)
            return False

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
