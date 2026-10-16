/**
 * Direct DB assertions for Playwright specs -- Neo4j (graph truth) and
 * Supabase Postgres (profiles/messages), bypassing the UI entirely. This is
 * what makes Playwright the "full-fidelity" suite vs. Maestro's UI-only
 * assertions (Maestro YAML has no first-class DB client).
 *
 * Node's neo4j-driver handles `neo4j+s://` natively -- unlike the backend's
 * Python driver, no TrustCustomCAs/certifi workaround is needed here (that
 * was a macOS-Python-specific cert-store issue, not a Node one).
 */
import { createClient } from '@supabase/supabase-js';
import neo4j, { type Driver } from 'neo4j-driver';

import { env } from './env';

let driver: Driver | undefined;

function getDriver(): Driver {
  driver ??= neo4j.driver(
    env.neo4jUri,
    neo4j.auth.basic(env.neo4jUser, env.neo4jPassword)
  );
  return driver;
}

export async function closeDb(): Promise<void> {
  await driver?.close();
  driver = undefined;
}

export const supabaseAdmin = createClient(env.supabaseUrl, env.supabaseServiceRoleKey);

/** Resolves the Supabase Auth user id (== Neo4j (:User).id, both are the
 * JWT `sub`) for a seeded test account's email. */
export async function userIdForEmail(email: string): Promise<string> {
  const { data, error } = await supabaseAdmin.auth.admin.listUsers();
  if (error) throw error;
  const user = data.users.find((u) => u.email === email);
  if (!user) throw new Error(`No Supabase user found for ${email}`);
  return user.id;
}

export async function expectUserNode(userId: string): Promise<boolean> {
  const session = getDriver().session();
  try {
    const result = await session.run('MATCH (u:User {id: $id}) RETURN u', { id: userId });
    return result.records.length === 1;
  } finally {
    await session.close();
  }
}

export async function fetchProfileRow(userId: string) {
  const { data, error } = await supabaseAdmin
    .from('profiles')
    .select('*')
    .eq('user_id', userId)
    .maybeSingle();
  if (error) throw error;
  return data;
}

export async function fetchSkillGraph(userId: string, skillName: string) {
  const session = getDriver().session();
  try {
    const result = await session.run(
      `MATCH (u:User {id: $userId})-[:PURSUES]->(s:Skill {name: $skillName})
       MATCH (s)-[:HAS_GOAL]->(g:Goal) WHERE NOT (g)<-[:SUPERSEDES]-(:Goal)
       MATCH (s)-[:HAS_PLAN]->(p:Plan) WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
       MATCH (p)-[:HAS_STEP]->(st:Step)
       RETURN s.id AS skillId, g.statement AS goalStatement, p.id AS planId,
              collect(st.order) AS stepOrders`,
      { userId, skillName }
    );
    return result.records[0] ?? null;
  } finally {
    await session.close();
  }
}

export async function fetchPlanGeneration(skillId: string): Promise<number | null> {
  const session = getDriver().session();
  try {
    const result = await session.run(
      `MATCH (s:Skill {id: $skillId})-[:HAS_PLAN]->(p:Plan)
       WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
       OPTIONAL MATCH path = (p)-[:SUPERSEDES*0..]->(:Plan)
       RETURN max(length(path)) AS generation`,
      { skillId }
    );
    const value = result.records[0]?.get('generation');
    return value === null || value === undefined ? null : Number(value);
  } finally {
    await session.close();
  }
}

/** CheckIns recorded against a skill's active plan (004) -- ordered
 * newest-first so callers can assert on the most recent report. */
export async function fetchCheckins(
  skillId: string
): Promise<{ stepOrder: number; outcome: string; sentiment: string; source: string }[]> {
  const session = getDriver().session();
  try {
    const result = await session.run(
      `MATCH (s:Skill {id: $skillId})-[:HAS_PLAN]->(p:Plan)
       WHERE NOT (p)<-[:SUPERSEDES]-(:Plan)
       MATCH (p)-[:HAS_STEP]->(st:Step)<-[:FOR_STEP]-(c:CheckIn)
       RETURN st.order AS stepOrder, c.outcome AS outcome, c.sentiment AS sentiment,
              c.source AS source, c.timestamp AS timestamp
       ORDER BY c.timestamp DESC`,
      { skillId }
    );
    return result.records.map((r) => ({
      stepOrder: Number(r.get('stepOrder')),
      outcome: r.get('outcome'),
      sentiment: r.get('sentiment'),
      source: r.get('source'),
    }));
  } finally {
    await session.close();
  }
}

export async function countSkillNodesNamed(userId: string, skillName: string): Promise<number> {
  const session = getDriver().session();
  try {
    const result = await session.run(
      `MATCH (u:User {id: $userId})-[:PURSUES]->(s:Skill {name: $skillName}) RETURN count(s) AS n`,
      { userId, skillName }
    );
    return Number(result.records[0]?.get('n') ?? 0);
  } finally {
    await session.close();
  }
}
