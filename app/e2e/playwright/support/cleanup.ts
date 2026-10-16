/**
 * Deletes ONLY what a given test run created -- scoped to the dedicated e2e
 * test accounts (fixtures/test-users.ts) and a run-tagged skill-name
 * prefix every spec must use (see `runPrefix` below). This is test-infra
 * teardown of synthetic data the run itself created, never a blanket wipe
 * of real user data -- distinct from the product's own no-delete-from-UI
 * rule (Constitution III is about what the app's UI exposes to a human, not
 * how automated test fixtures clean up after themselves). Flagged
 * explicitly in the test-automation backfill plan for this reason.
 */
import neo4j from 'neo4j-driver';

import { supabaseAdmin } from './db';
import { env } from './env';

/** Unique per test run so parallel/re-run specs never collide or delete
 * each other's data; also makes leftover data from a crashed run easy to
 * spot and manually clean up (searchable by prefix in the Aura console). */
export function runPrefix(): string {
  return `[e2e-pw]-${Date.now()}-${Math.random().toString(36).slice(2, 8)}-`;
}

export async function cleanupSkillsByPrefix(userId: string, prefix: string): Promise<void> {
  const driver = neo4j.driver(env.neo4jUri, neo4j.auth.basic(env.neo4jUser, env.neo4jPassword));
  const session = driver.session();
  try {
    const found = await session.run(
      `MATCH (u:User {id: $userId})-[:PURSUES]->(s:Skill)
       WHERE s.name STARTS WITH $prefix
       RETURN s.id AS id`,
      { userId, prefix }
    );
    const skillIds = found.records.map((r) => r.get('id') as string);

    if (skillIds.length > 0) {
      const { error } = await supabaseAdmin.from('messages').delete().in('skill_id', skillIds);
      if (error) throw error;
    }

    await session.run(
      `MATCH (u:User {id: $userId})-[:PURSUES]->(s:Skill)
       WHERE s.name STARTS WITH $prefix
       OPTIONAL MATCH (s)-[:HAS_GOAL]->(g:Goal)
       OPTIONAL MATCH (s)-[:HAS_PLAN]->(p:Plan)
       OPTIONAL MATCH (p)-[:HAS_STEP]->(st:Step)
       OPTIONAL MATCH (st)<-[:FOR_STEP]-(c:CheckIn)
       DETACH DELETE s, g, p, st, c`,
      { userId, prefix }
    );
  } finally {
    await session.close();
    await driver.close();
  }
}

/** For specs that never got far enough to create a skill (e.g. the
 * abandon-profile scenario) -- just clears any general (skill_id IS NULL)
 * messages for the account so repeated runs start clean. */
export async function cleanupGeneralMessages(userId: string): Promise<void> {
  const { error } = await supabaseAdmin
    .from('messages')
    .delete()
    .eq('user_id', userId)
    .is('skill_id', null);
  if (error) throw error;
}
