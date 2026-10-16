# Restore Runbook

Tested procedure for replaying a nightly graph export (005, research.md
R5) into a Neo4j instance. Required once before the first pilot invite
(SC-003) and available at any real-incident recovery need.

## Prerequisites

- A **scratch Neo4j instance separate from the live one** — never
  restore directly on top of the live instance; the script refuses a
  non-empty target by default specifically to prevent this. Aura Free
  is capped at 1 instance per account, so a genuinely free scratch
  target is a **local Neo4j via Docker** (`docker run -d --name
  neo4j-scratch -p 7688:7687 -e NEO4J_AUTH=neo4j/<password> neo4j:5`,
  then `--uri bolt://localhost:7688`) — a second cloud Aura instance
  needs either a paid tier or a separate account, and the restore
  script only needs a real Bolt endpoint, not specifically Aura.
- The dated export artifact downloaded from the private `graph-exports`
  Supabase Storage bucket (Supabase dashboard → Storage →
  `graph-exports` → download `graph-export-YYYY-MM-DD.json`), or fetched
  via the Storage REST API with the service-role key.
- `api/`: `uv sync --frozen`.

## Procedure

1. Create (or reuse) the scratch Aura instance; note its connection URI,
   username (the instance id, per this project's existing Aura
   convention — see `docs/skill-coach-development-plan.md`), and
   password.
2. Download a real nightly artifact from the `graph-exports` bucket.
3. Run the restore script:

   ```bash
   cd api
   uv run python scripts/restore_graph.py \
     --file /path/to/graph-export-2026-07-19.json \
     --uri neo4j+s://<scratch-instance-id>.databases.neo4j.io \
     --user <scratch-instance-id> \
     --password <scratch-password>
   ```

4. The script refuses to run if the target already has any nodes
   (safety check) — pass `--force-empty-check-off` only if you have
   deliberately decided to restore into a non-empty instance (not the
   normal case).
5. On success, the script prints the restored node/relationship counts
   and confirms they match the artifact's own independently-aggregated
   `counts` field (SC-003's spot-check — the count comparison is against
   a number the row-by-row replay didn't itself produce, so a subtle
   replay bug can't silently pass).
6. **Spot-check one user's data directly** against the scratch instance
   (Neo4j Browser or `cypher-shell`):

   ```cypher
   MATCH (u:User {id: '<a-real-user-id-from-the-export>'})-[:PURSUES]->(s:Skill)
   RETURN s.name, s.id;

   MATCH (u:User {id: '<same-user-id>'})-[:PURSUES]->(:Skill)-[:HAS_PLAN]->(p:Plan)
   WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
   MATCH (p)-[:HAS_STEP]->(st:Step)
   RETURN st.order, st.description;
   ```

   Confirm the skills/plans/steps match what you'd expect from the live
   instance at export time.
7. Tear down the scratch instance once satisfied (Aura Free instances
   are free, but there's no reason to keep a second one running).

## Rehearsal log

Record every real rehearsal here (date, artifact used, outcome) — SC-003
requires at least one before the first pilot invite.

| Date | Artifact | Outcome | Notes |
|------|----------|---------|-------|
| 2026-08-26 | `graph-export-2026-08-26.json` (154 nodes, 167 relationships) | ✅ succeeded on the second attempt | First attempt against a local Neo4j (Docker) scratch instance crashed with `DateTime string is not in ISO format` after writing 3 nodes -- found and fixed two real bugs in `export_graph.py`/`restore_graph.py` (untagged `Date`/`Time`/`DateTime` serialization, and a deserialization error surfacing mid-write instead of during upfront validation; see that commit). Re-ran after the fix and a fresh export: counts matched the artifact's independent aggregation exactly, and a spot-check of one real user (`bcb80d9b-...`) showed correct, coherent skills/plans/steps (including a Hindi-language cricket plan alongside English swimming/football plans). Scratch container torn down after. |
