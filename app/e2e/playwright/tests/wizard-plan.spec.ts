import { expect, Page, test } from '@playwright/test';

import { PW2 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { sendMessage } from '../support/chat';
import { cleanupSkillsByPrefix, runPrefix } from '../support/cleanup';
import {
  countSkillNodesNamed,
  fetchPlanGeneration,
  fetchSkillGraph,
  userIdForEmail,
} from '../support/db';
import { completeWizard } from '../support/wizard';

const SCRIPTED_ANSWERS = [
  "Hi, I'd like to start learning to swim.",
  "I'm a complete beginner, I've never swum laps before.",
];

/** Reveals the regenerate box if needed, picks a reason, submits, and
 * waits for the real /plan/regenerate response. */
async function regenerate(page: Page, reason: string): Promise<void> {
  const revealLink = page.getByText('Want to adjust this plan?');
  await revealLink.click({ timeout: 10_000 });
  await page.getByRole('radio', { name: reason }).click({ timeout: 10_000 });

  await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/plan/regenerate') && res.request().method() === 'POST',
      { timeout: 30_000 }
    ),
    page.getByRole('button', { name: 'Regenerate' }).click(),
  ]);
}

test.describe('002 Wizard & Plan', () => {
  test('wizard conversation creates a goal+plan atomically (quickstart #1-3)', async ({ page }) => {
    test.setTimeout(120_000); // multiple real LLM turns, each can take several seconds
    const prefix = runPrefix();
    const skillName = `${prefix}Swimming`;
    const userId = await userIdForEmail(PW2.email);

    try {
      await signInAsUser(page, PW2);
      await page.goto('/skills');
      await page.waitForURL('**/skills');

      await completeWizard(page, skillName);
      await expect(page.getByText('Your plan')).toBeVisible();

      const graph = await fetchSkillGraph(userId, skillName);
      expect(graph, 'goal+plan+steps should exist atomically in the graph').toBeTruthy();
      const stepOrders = graph!.get('stepOrders') as number[];
      expect(stepOrders.length).toBeGreaterThanOrEqual(3);
      expect(stepOrders.length).toBeLessThanOrEqual(12);
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });

  test('abandoning the wizard mid-conversation leaves no orphaned skill (quickstart #4)', async ({
    page,
  }) => {
    const prefix = runPrefix();
    const skillName = `${prefix}Chess`;
    const userId = await userIdForEmail(PW2.email);

    try {
      await signInAsUser(page, PW2);
      await page.goto('/skills');
      await page.waitForURL('**/skills');

      await page.getByRole('button', { name: 'Add skill' }).click();
      await page.getByRole('textbox').fill(skillName);
      await page.getByRole('button', { name: 'Continue' }).click();
      await page.waitForURL('**/wizard**');

      // One turn in, then abandon -- create_skill/create_plan only ever
      // apply atomically at the wizard's own confirmation step, so a
      // half-finished conversation should leave nothing behind.
      await sendMessage(page, SCRIPTED_ANSWERS[0]);
      await page.goto('/skills');
      await page.waitForURL('**/skills');

      expect(await countSkillNodesNamed(userId, skillName)).toBe(0);
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });

  test('regenerate: too_much then too_easy then cap at 3 attempts (quickstart #5-7)', async ({
    page,
  }) => {
    test.setTimeout(300_000); // wizard completion + 3 real regenerate calls, each can retry once internally
    const prefix = runPrefix();
    const skillName = `${prefix}Running`;
    const userId = await userIdForEmail(PW2.email);

    try {
      await signInAsUser(page, PW2);
      await page.goto('/skills');
      await page.waitForURL('**/skills');
      await completeWizard(page, skillName);
      // plan-review's own GET /v1/skills/{id} is async and separate from
      // the wizard's navigation -- wait for it to settle before
      // interacting, or the reveal-link/radio locators below can poll
      // against not-yet-rendered elements for the full test timeout
      // instead of failing fast.
      await expect(page.getByText('Your plan')).toBeVisible();

      const graph = await fetchSkillGraph(userId, skillName);
      const skillId = graph!.get('skillId') as string;
      expect(await fetchPlanGeneration(skillId)).toBe(0);

      await regenerate(page, 'Too much');
      expect(await fetchPlanGeneration(skillId)).toBe(1);

      await regenerate(page, 'Too easy');
      expect(await fetchPlanGeneration(skillId)).toBe(2);

      await regenerate(page, 'Not quite right');
      expect(await fetchPlanGeneration(skillId)).toBe(3);

      // Client hides the option once generation >= 3 (server still enforces).
      await expect(page.getByText('Want to adjust this plan?')).toHaveCount(0);
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });

  test('adding a duplicate skill name (any case) warns before starting a new wizard (quickstart #8)', async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const prefix = runPrefix();
    const skillName = `${prefix}Chess`;
    const userId = await userIdForEmail(PW2.email);

    try {
      await signInAsUser(page, PW2);
      await page.goto('/skills');
      await page.waitForURL('**/skills');
      await completeWizard(page, skillName);

      // Back to the home dashboard, try adding the same name lowercased.
      // Wait for the card itself (not just the URL) -- the skills list
      // fetch is async, and adding before it resolves would race
      // findDuplicate against an empty list.
      await page.goto('/skills');
      await expect(page.getByText(skillName)).toBeVisible();
      await page.getByRole('button', { name: 'Add skill' }).click();
      await page.getByRole('textbox').fill(skillName.toLowerCase());
      await page.getByRole('button', { name: 'Continue' }).click();

      await expect(page.getByText('Already learning this?')).toBeVisible();
      await page.getByText('Continue existing').click();
      await page.waitForURL('**/plan-review**');
      await expect(page.getByText('Your plan')).toBeVisible();

      // Only the one skill exists -- "Continue existing" must not have
      // started a second wizard/skill under the lowercased name.
      expect(await countSkillNodesNamed(userId, skillName)).toBe(1);
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });
});
