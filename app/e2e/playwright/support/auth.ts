/**
 * Session-injection: signs in a seeded test user via a plain (non-browser)
 * Supabase client, then seeds the resulting session into the page's
 * localStorage before any app script runs, so the app boots already
 * authenticated. Skips driving the sign-in UI for specs that aren't
 * specifically testing auth itself (mirrors the web storage key Supabase JS
 * uses by default -- see app/src/lib/supabase.ts, no custom `storage` for
 * Platform.OS === 'web').
 */
import type { Page } from '@playwright/test';
import { createClient } from '@supabase/supabase-js';

import type { TestUser } from '../fixtures/test-users';
import { env } from './env';

function storageKey(): string {
  const ref = new URL(env.supabaseUrl).hostname.split('.')[0];
  return `sb-${ref}-auth-token`;
}

// 005, research.md R12: the first-run welcome explainer shows once per
// fresh AsyncStorage (== fresh browser context here, since every existing
// spec expects signInAsUser to land past onboarding, not detour through
// /welcome first) -- pre-seed the same flag welcome.tsx itself writes
// (lib/onboarding.ts) so every OTHER spec's behavior is unaffected.
// Specs that specifically test onboarding (onboarding-005.spec.ts) skip
// this helper and drive a real fresh signup instead.
const WELCOME_SEEN_KEY = 'skillcoach.onboarding-welcome-seen.v1';

export async function signInAsUser(
  page: Page,
  user: TestUser,
  options?: { skipWelcomeSeed?: boolean }
): Promise<string> {
  const client = createClient(env.supabaseUrl, env.supabaseAnonKey);
  const { data, error } = await client.auth.signInWithPassword(user);
  if (error || !data.session) {
    throw new Error(`Could not sign in seeded test user ${user.email}: ${error?.message}`);
  }

  const key = storageKey();
  const value = JSON.stringify(data.session);
  const seedWelcome = !options?.skipWelcomeSeed;
  await page.addInitScript(
    ([storageKey, sessionValue, welcomeSeenKey, seedWelcomeFlag]) => {
      window.localStorage.setItem(storageKey, sessionValue);
      if (seedWelcomeFlag === 'true') {
        window.localStorage.setItem(welcomeSeenKey, 'true');
      }
    },
    [key, value, WELCOME_SEEN_KEY, String(seedWelcome)]
  );

  return data.session.user.id;
}
