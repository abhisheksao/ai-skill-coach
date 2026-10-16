import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { expectUserNode, fetchProfileRow } from '../support/db';
import { createThrowawayUser, deleteThrowawayUser } from '../support/throwaway-user';

/** Feature 001 quickstart scenarios that are provable on web. Cross-platform
 * (iOS/Android-specific) scenarios and ones already proven at the API layer
 * (test_tenancy.py, test_budget.py) stay in the manual checklist -- see
 * docs/testing.md. */

test.describe('001 Foundations', () => {
  test('fresh account: profile step completes, lands on the dashboard, (:User) exists (quickstart #1 web variant, FR-010/011/012)', async ({
    page,
  }) => {
    const user = await createThrowawayUser();
    try {
      await signInAsUser(page, user);
      await page.goto('/');

      await expect(page.getByText('Almost there')).toBeVisible();
      await page.getByRole('checkbox').click();
      await page.getByRole('button', { name: 'Continue' }).click();

      // 004: the home dashboard replaces /skills as the post-profile landing.
      await page.waitForURL('**/dashboard', { timeout: 15_000 });

      await expect(async () => {
        expect(await fetchProfileRow(user.id)).toBeTruthy();
      }).toPass({ timeout: 10_000 });
      expect(await expectUserNode(user.id)).toBe(true);
    } finally {
      await deleteThrowawayUser(user.id);
    }
  });

  test('fresh account: abandoning the profile step keeps it re-presented, no profile row written (quickstart #5)', async ({
    page,
  }) => {
    const user = await createThrowawayUser();
    try {
      await signInAsUser(page, user);
      await page.goto('/');
      await expect(page.getByText('Almost there')).toBeVisible();

      // Abandon: reload without submitting.
      await page.reload();

      await expect(page.getByText('Almost there')).toBeVisible();
      expect(await fetchProfileRow(user.id)).toBeNull();
    } finally {
      await deleteThrowawayUser(user.id);
    }
  });

  test('existing account: session survives a reload (quickstart #3)', async ({ page }) => {
    await signInAsUser(page, PW1);
    await page.goto('/skills');
    await expect(page).toHaveURL(/\/skills/);

    await page.reload();

    // A dropped session would bounce to /sign-in; a kept one stays put.
    await expect(page).toHaveURL(/\/skills/);
    await expect(page.getByText('Skill Coach')).toBeVisible();
  });
});
