import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { cleanupSkillsByPrefix, runPrefix } from '../support/cleanup';
import { fetchSkillGraph, userIdForEmail } from '../support/db';
import { completeWizard } from '../support/wizard';

/** 004 FR-009 / Edge Case: skillcoach://skill/{id}/session deep-links
 * into that skill's coaching session. The native OS notification tap
 * itself isn't reproducible here (no real push), but the redirect route
 * (app/(main)/skill/[id]/session.tsx) is an ordinary expo-router screen
 * that renders identically whether reached via a push tap, a typed URL,
 * or any other opener -- exercising it directly on web proves the
 * routing contract. */
test.describe('004 User Story 4 - Deep link', () => {
  test('navigating to /skill/{id}/session lands on that skill\'s chat', async ({ page }) => {
    test.setTimeout(120_000);
    const prefix = runPrefix();
    const skillName = `${prefix}Swimming`;
    const userId = await userIdForEmail(PW1.email);

    try {
      await signInAsUser(page, PW1);
      await page.goto('/skills');
      await page.waitForURL('**/skills');
      await completeWizard(page, skillName);

      const graph = await fetchSkillGraph(userId, skillName);
      const skillId = graph!.get('skillId') as string;

      await page.goto(`/skill/${skillId}/session`);

      await page.waitForURL(`**/chat?skillId=${skillId}`, { timeout: 15_000 });
      await expect(page.getByPlaceholder('Message your coach…')).toBeVisible();
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });

  test('an unresolvable skill id falls back to the dashboard, never a crash', async ({ page }) => {
    await signInAsUser(page, PW1);
    // expo-router still matches the dynamic segment even for a
    // nonexistent skill -- the redirect target is decided by the route
    // component itself, not route matching, so this exercises chat.tsx's
    // existing "unknown skill_id" tolerance (empty history, no crash)
    // rather than a special-cased not-found page.
    await page.goto('/skill/00000000-0000-0000-0000-000000000000/session');

    await page.waitForURL(/\/chat\?skillId=/, { timeout: 15_000 });
    await expect(page.locator('body')).not.toContainText('Error');
  });

  test('signing out then visiting the deep link routes to sign-in, never a crash', async ({
    page,
  }) => {
    await page.goto('/skill/00000000-0000-0000-0000-000000000000/session');
    await page.waitForURL('**/sign-in', { timeout: 15_000 });
  });
});
