// 001 Foundations: (:User) uniqueness (specs/001-foundations/data-model.md)
// Apply with: cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
//   -f api/migrations/neo4j/001_init.cypher

CREATE CONSTRAINT user_id_unique IF NOT EXISTS
FOR (u:User) REQUIRE u.id IS UNIQUE;
