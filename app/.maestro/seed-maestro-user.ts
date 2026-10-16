/**
 * Idempotent: creates the dedicated Maestro test account
 * (MAESTRO_EMAIL/MAESTRO_PASSWORD, see .maestro/.env.example) if it
 * doesn't already exist, and ensures its profile step is complete --
 * same approach as e2e/playwright/support/seed-test-users.ts, reusing
 * its Supabase Admin API helpers directly (same project, no duplication).
 * Run once manually:
 *
 *   npx tsx .maestro/seed-maestro-user.ts
 */
import { config } from 'dotenv';
import path from 'node:path';

import { supabaseAdmin } from '../e2e/playwright/support/db';
import { ensureCompletedProfile } from '../e2e/playwright/support/profile-setup';

config({ path: path.resolve(__dirname, '.env') });
// e2e/playwright/support/env.ts reads E2E_-prefixed vars; reuse the same
// live Supabase project by pointing those at the values already in
// e2e/playwright/.env rather than duplicating secrets in .maestro/.env.
config({ path: path.resolve(__dirname, '../e2e/playwright/.env') });

async function main(): Promise<void> {
  const email = process.env.MAESTRO_EMAIL;
  const password = process.env.MAESTRO_PASSWORD;
  if (!email || !password) {
    throw new Error('Set MAESTRO_EMAIL/MAESTRO_PASSWORD in .maestro/.env (copy from .env.example).');
  }

  const { data, error } = await supabaseAdmin.auth.admin.listUsers();
  if (error) throw error;

  let userId = data.users.find((u) => u.email === email)?.id;
  if (userId) {
    console.log(`already exists: ${email}`);
  } else {
    const { data: created, error: createError } = await supabaseAdmin.auth.admin.createUser({
      email,
      password,
      email_confirm: true,
    });
    if (createError || !created.user) throw createError;
    userId = created.user.id;
    console.log(`created: ${email}`);
  }

  await ensureCompletedProfile({ email, password }, userId);
  console.log('profile ensured');
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
