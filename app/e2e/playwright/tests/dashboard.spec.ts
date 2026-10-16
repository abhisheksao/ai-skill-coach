import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { cleanupSkillsByPrefix, runPrefix } from '../support/cleanup';
import { fetchCheckins, fetchSkillGraph, userIdForEmail } from '../support/db';
import { completeWizard } from '../support/wizard';

/** 004 User Story 6: signing in now lands on the home dashboard
 * (index.tsx/_layout.tsx redirect target changed from /skills), showing
 * a card per skill with goal/plan/progress. The offline stale-data cache
 * fallback itself (research.md R10) is unit-tested directly against
 * dashboard-cache.ts (app/src/lib/dashboard-cache.test.ts) rather than
 * simulated here via network interception -- this spec proves the
 * redirect + card rendering end to end instead. */
test.describe('004 User Story 6 - Home dashboard', () => {
  test('signing in with no skills lands on the dashboard empty state', async ({ page }) => {
    await signInAsUser(page, PW1);
    await page.goto('/');

    await page.waitForURL('**/dashboard', { timeout: 15_000 });
    // Either the empty state or existing cards render -- PW1 is a shared
    // account other specs also use, so it may already have skills from a
    // prior run; either way this proves the dashboard screen itself loads.
    await expect(page.getByText('Skill Coach')).toBeVisible();
  });

  test('a skill created via the wizard appears as a dashboard card', async ({ page }) => {
    test.setTimeout(120_000);
    const prefix = runPrefix();
    const skillName = `${prefix}Chess`;
    const userId = await userIdForEmail(PW1.email);

    try {
      await signInAsUser(page, PW1);
      await page.goto('/dashboard');
      await page.waitForURL('**/dashboard');
      await completeWizard(page, skillName);

      await page.goto('/dashboard');
      await expect(page.getByText(skillName)).toBeVisible({ timeout: 15_000 });
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });
});

/** 004 User Story 7: tap-to-complete/log-partial directly from a
 * dashboard card, bypassing the LLM entirely (SC-007). The zero-LLM-call
 * guarantee and the "source is always ui_tap" guarantee are already
 * proven at the API contract level (test_checkins_contract.py); this
 * spec proves the actual UI wiring -- tapping the real button reaches
 * the real endpoint and the card updates immediately. */
test.describe('004 User Story 7 - Tap-to-complete on the dashboard', () => {
  test('tapping "Mark complete" records a completed CheckIn and updates the card', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const prefix = runPrefix();
    const skillName = `${prefix}Chess`;
    const userId = await userIdForEmail(PW1.email);

    try {
      await signInAsUser(page, PW1);
      await page.goto('/dashboard');
      await page.waitForURL('**/dashboard');
      await completeWizard(page, skillName);

      const graph = await fetchSkillGraph(userId, skillName);
      const skillId = graph!.get('skillId') as string;

      await page.goto('/dashboard');
      // PW1 is a shared account that accumulates many skill cards across
      // runs -- "Mark complete" repeats once per incomplete step across
      // ALL of them, so `.first()` on that text alone is genuinely
      // ambiguous and can click a DIFFERENT skill's step (found live,
      // 2026-07-18, running this spec for the first time ever: the
      // checkin landed against some other skill, this one's stayed
      // empty). Scope to this run's card specifically via testID.
      const card = page.getByTestId(`dashboard-card-${skillId}`);
      await expect(card.getByText(skillName)).toBeVisible({ timeout: 15_000 });
      const markComplete = card.getByText('Mark complete').first();
      await expect(markComplete).toBeVisible();

      await Promise.all([
        page.waitForResponse(
          (res) => res.url().includes('/v1/intents/apply') && res.request().method() === 'POST'
        ),
        markComplete.click(),
      ]);

      await expect
        .poll(async () => fetchCheckins(skillId), { timeout: 15_000 })
        .not.toHaveLength(0);
      const checkins = await fetchCheckins(skillId);
      expect(checkins[0].source).toBe('ui_tap');
      expect(checkins[0].outcome).toBe('completed');

      // The dashboard refetches after a successful tap -- the card now
      // shows one completed step.
      await expect(page.getByText(/1 of \d+ steps complete/)).toBeVisible({ timeout: 10_000 });
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });
});
