import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';

/** 005 US1 scenario 2: budget exhaustion renders as an ordinary
 * in-conversation coach bubble, localized with the reset time, and the
 * composer stays enabled -- never a raw error. Mocks POST /v1/chat's
 * response shape directly (contracts/api.md) rather than actually
 * draining a real budget, which would burn live LLM quota for no
 * reason -- this is a pure client-rendering contract. */
test.describe('005 User Story 1 - Budget-exhausted turn', () => {
  test('renders as a coach bubble with a localized reset time; composer stays enabled', async ({
    page,
  }) => {
    await signInAsUser(page, PW1);

    await page.route('**/v1/chat', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          reply: 'errors.budget_exhausted_reply',
          session_id: '00000000-0000-0000-0000-0000000000b1',
          skill_id: null,
          intents: [],
          suggested_replies: [],
          budget: { exhausted: true, resets_at: '2026-07-19T00:00:00Z' },
        }),
      });
    });

    await page.goto('/skills');
    await page.getByRole('button', { name: 'Add skill' }).click();
    await page.getByRole('textbox').fill('Budget Test Skill');
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForURL('**/wizard**');

    const input = page.getByPlaceholder('Message your coach…');
    await input.fill('hello coach');
    await page.getByRole('button', { name: 'Send' }).click();

    // Renders as a normal coach bubble -- localized, not the raw i18n
    // key, and carries a human-formatted reset time (never the raw ISO
    // timestamp the mock returned).
    await expect(page.getByText(/reached today's conversation limit/i)).toBeVisible();
    await expect(page.getByText('errors.budget_exhausted_reply')).not.toBeVisible();
    await expect(page.getByText('2026-07-19T00:00:00Z')).not.toBeVisible();

    // Never disabled -- the user can keep chatting immediately.
    await expect(input).toBeEnabled();
  });
});
