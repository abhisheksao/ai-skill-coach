/**
 * Idempotent: creates the two dedicated, pre-confirmed Playwright test
 * accounts if they don't already exist. Run once manually:
 *
 *   npx tsx e2e/playwright/support/seed-test-users.ts
 *
 * Uses the Supabase service-role key (same one already in api/.env) to call
 * the Auth Admin API with `email_confirm: true`, skipping the "check your
 * email" branch entirely -- no real email is ever sent.
 */
import { PW1, PW2 } from '../fixtures/test-users';
import { supabaseAdmin } from './db';
import { requireEnv } from './env';
import { ensureCompletedProfile } from './profile-setup';

async function ensureUser(email: string, password: string): Promise<string> {
  const { data, error } = await supabaseAdmin.auth.admin.listUsers();
  if (error) throw error;

  const existing = data.users.find((u) => u.email === email);
  if (existing) {
    console.log(`already exists: ${email}`);
    return existing.id;
  }

  const { data: created, error: createError } = await supabaseAdmin.auth.admin.createUser({
    email,
    password,
    email_confirm: true,
  });
  if (createError || !created.user) throw createError;
  console.log(`created: ${email}`);
  return created.user.id;
}

async function main(): Promise<void> {
  // Only what account creation itself needs -- not Neo4j, which this
  // script never touches (unlike db.ts's DB-assertion helpers).
  requireEnv('E2E_SUPABASE_URL');
  requireEnv('E2E_SUPABASE_SERVICE_ROLE_KEY');
  const id1 = await ensureUser(PW1.email, PW1.password);
  const id2 = await ensureUser(PW2.email, PW2.password);

  // Most specs assume a past-onboarding account; complete the profile step
  // directly via the API (idempotent) rather than relying on the account
  // having been driven through the UI before.
  await ensureCompletedProfile(PW1, id1);
  await ensureCompletedProfile(PW2, id2);
  console.log('profiles ensured for both accounts');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
