/**
 * PW1/PW2 (fixtures/test-users.ts) are reused across every run and already
 * have a completed profile -- they can't exercise first-run flows (fresh
 * signup, the profile step, "abandoned profile step" re-presentation).
 * These create/delete a real, one-off Supabase Auth user via the Admin API
 * (email_confirm: true, same approach as seed-test-users.ts) for specs that
 * need a truly blank identity.
 */
import neo4j from 'neo4j-driver';

import { supabaseAdmin } from './db';
import { env } from './env';

export type ThrowawayUser = { id: string; email: string; password: string };

export async function createThrowawayUser(): Promise<ThrowawayUser> {
  const email = `e2e-throwaway-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@skillcoach.test`;
  const password = 'Throwaway-Password-1!';
  const { data, error } = await supabaseAdmin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });
  if (error || !data.user) {
    throw new Error(`Could not create throwaway user: ${error?.message}`);
  }
  return { id: data.user.id, email, password };
}

/** Deletes the auth user (Postgres `profiles`/`messages` cascade via FK --
 * see supabase/migrations) and its Neo4j (:User) node, if one was created. */
export async function deleteThrowawayUser(id: string): Promise<void> {
  const { error } = await supabaseAdmin.auth.admin.deleteUser(id);
  if (error) throw error;

  const driver = neo4j.driver(env.neo4jUri, neo4j.auth.basic(env.neo4jUser, env.neo4jPassword));
  const session = driver.session();
  try {
    await session.run('MATCH (u:User {id: $id}) DETACH DELETE u', { id });
  } finally {
    await session.close();
    await driver.close();
  }
}
