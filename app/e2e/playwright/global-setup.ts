import { requireEnv } from './support/env';

/** Only checks the vars every spec needs regardless of what it tests
 * (Supabase URL/anon key, for loading the app and/or signing in). Specs
 * that also need Neo4j assertions or a specific seeded account fail with
 * their own clear per-var error via env.ts's lazy getters -- no need to
 * force every var present just to run, say, the plain smoke spec. */
export default async function globalSetup(): Promise<void> {
  requireEnv('E2E_SUPABASE_URL');
  requireEnv('E2E_SUPABASE_ANON_KEY');
}
