/**
 * Ensures a seeded test account has completed the profile step, via a
 * direct POST /v1/profile call (idempotent -- contract test 3) rather than
 * driving the onboarding UI. PW1/PW2 (fixtures/test-users.ts) are created
 * by seed-test-users.ts, which only touches Supabase Auth -- without this,
 * every spec that assumes "an existing, past-onboarding user" would land
 * on the profile step instead.
 */
import { createClient } from '@supabase/supabase-js';

import type { TestUser } from '../fixtures/test-users';
import { env } from './env';
import { fetchProfileRow } from './db';

export async function ensureCompletedProfile(user: TestUser, userId: string): Promise<void> {
  if (await fetchProfileRow(userId)) return;

  const client = createClient(env.supabaseUrl, env.supabaseAnonKey);
  const { data, error } = await client.auth.signInWithPassword(user);
  if (error || !data.session) {
    throw new Error(`Could not sign in ${user.email} to seed a profile: ${error?.message}`);
  }

  const response = await fetch(`${env.apiUrl}/v1/profile`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${data.session.access_token}`,
    },
    body: JSON.stringify({
      display_name: null,
      language: 'en',
      timezone: 'UTC',
      consent: true,
    }),
  });
  if (!response.ok) {
    throw new Error(`Profile seed failed for ${user.email}: ${response.status} ${await response.text()}`);
  }
}
