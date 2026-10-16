import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { createThrowawayUser, deleteThrowawayUser } from '../support/throwaway-user';

/** 005 US5 -- first-run onboarding explainer + Settings' delete-account
 * entry (research.md R12/R13). The explainer needs a genuinely fresh
 * identity (no onboarding-welcome-seen flag) -- PW1/PW2 are pre-seeded
 * PAST onboarding by signInAsUser for every other spec's sake (see that
 * helper's own comment), so these two tests explicitly opt out via
 * skipWelcomeSeed. */
test.describe('005 User Story 5 - Onboarding & deletion entry', () => {
  test('first-run explainer appears after profile completion, walks through both cards, enables nudges, and completes into the dashboard -- never shown again after', async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const user = await createThrowawayUser();
    try {
      await signInAsUser(page, user, { skipWelcomeSeed: true });
      await page.goto('/');

      await expect(page.getByText('Almost there')).toBeVisible();
      await page.getByRole('checkbox').click();
      await page.getByRole('button', { name: 'Continue' }).click();

      // Welcome explainer -- NOT the dashboard yet.
      await page.waitForURL('**/welcome', { timeout: 15_000 });
      await expect(page.getByText('Hold to speak')).toBeVisible();

      await page.getByRole('button', { name: 'Continue' }).click();
      await expect(page.getByText('Stay on track')).toBeVisible();

      await page.getByRole('button', { name: 'Enable nudges' }).click();
      await page.waitForURL('**/dashboard', { timeout: 15_000 });

      // Never shown again: navigating back to /welcome directly bounces
      // straight to the dashboard instead of re-rendering the explainer.
      await page.goto('/welcome');
      await page.waitForURL('**/dashboard', { timeout: 15_000 });
    } finally {
      await deleteThrowawayUser(user.id);
    }
  });

  test('skipping the explainer still lands on the dashboard and marks it seen', async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const user = await createThrowawayUser();
    try {
      await signInAsUser(page, user, { skipWelcomeSeed: true });
      await page.goto('/');

      await expect(page.getByText('Almost there')).toBeVisible();
      await page.getByRole('checkbox').click();
      await page.getByRole('button', { name: 'Continue' }).click();

      await page.waitForURL('**/welcome', { timeout: 15_000 });
      await page.getByRole('button', { name: 'Skip' }).click();
      await page.waitForURL('**/dashboard', { timeout: 15_000 });

      await page.goto('/welcome');
      await page.waitForURL('**/dashboard', { timeout: 15_000 }); // never shown again
    } finally {
      await deleteThrowawayUser(user.id);
    }
  });

  test('Settings -> Delete account opens the configured URL in a new tab, without navigating away', async ({
    page,
  }) => {
    await signInAsUser(page, PW1);
    await page.goto('/settings');
    await expect(page.getByText('Settings')).toBeVisible();

    const [popup] = await Promise.all([
      page.waitForEvent('popup'),
      page.getByText('Delete account').click(),
    ]);
    await popup.waitForLoadState();
    expect(popup.url()).toContain('skillcoach-delete-account');
    await popup.close();

    // The settings screen itself never navigated away.
    await expect(page).toHaveURL(/\/settings/);
  });
});
