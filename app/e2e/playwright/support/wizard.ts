import { expect, Page } from '@playwright/test';

import { sendMessage } from './chat';

const MAX_WIZARD_TURNS = 10;
const SCRIPTED_ANSWERS = [
  "Hi, I'd like to start learning to swim.",
  "I'm a complete beginner, I've never swum laps before.",
  'I want to be able to swim 20 laps of freestyle without stopping.',
  'In 3 months.',
  '3 times a week, 30 minutes each session.',
  "Yes, that's right, please go ahead.",
  'Yes, looks good.',
  'Confirm.',
];

/** Drives the wizard from the /skills "Add skill" FAB to a resolved
 * skill_id, returning once plan-review has taken over. Scripted answers
 * are generic enough for the real (non-deterministic) LLM to reliably
 * reach create_skill+create_plan within MAX_WIZARD_TURNS. Shared across
 * 002's own spec and every later feature that needs an existing skill+plan
 * as a precondition (004's check-in/progress/dashboard specs). */
export async function completeWizard(page: Page, skillName: string): Promise<void> {
  await page.getByRole('button', { name: 'Add skill' }).click();
  await page.getByRole('textbox').fill(skillName);
  await page.getByRole('button', { name: 'Continue' }).click();
  await page.waitForURL('**/wizard**');

  let skillId: string | null = null;
  for (let i = 0; i < MAX_WIZARD_TURNS && !skillId; i++) {
    const answer = SCRIPTED_ANSWERS[Math.min(i, SCRIPTED_ANSWERS.length - 1)];
    const result = await sendMessage(page, answer);
    skillId = result.skill_id;
  }
  expect(skillId, 'wizard should resolve a skill_id within the scripted turns').toBeTruthy();
  await page.waitForURL('**/plan-review**', { timeout: 15_000 });
}
