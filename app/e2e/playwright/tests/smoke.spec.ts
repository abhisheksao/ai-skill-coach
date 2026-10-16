import { expect, test } from '@playwright/test';

/** Proves the harness end-to-end (build -> serve -> Playwright drives a
 * real browser against it) before any scenario coverage is written. */
test('app loads and shows the sign-in screen', async ({ page }) => {
  await page.goto('/sign-in');
  await expect(page.getByRole('button', { name: 'Sign in' })).toBeVisible();
});
