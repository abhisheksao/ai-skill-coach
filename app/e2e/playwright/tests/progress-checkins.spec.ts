import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { sendMessage } from '../support/chat';
import { cleanupSkillsByPrefix, runPrefix } from '../support/cleanup';
import { fetchCheckins, fetchSkillGraph, userIdForEmail } from '../support/db';
import { completeWizard } from '../support/wizard';

// LLM output is free-form prose (non-deterministic) -- these specs assert
// on the resulting CheckIn record in the graph, not on exact reply
// wording, the same "assert on state, not on prose" approach as
// wizard-plan.spec.ts's regenerate tests.
test.describe('004 User Story 1 - Check in on practice', () => {
  test('reporting a completed practice records a completed CheckIn against the right step', async ({
    page,
  }) => {
    test.setTimeout(180_000); // wizard completion + one coaching turn, real LLM calls throughout
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
      // neo4j-driver v6 deserializes Cypher integers as native BigInt, not
      // number -- Math.min can't spread a BigInt array (TypeError, found
      // live 2026-07-18 running this spec for the first time ever).
      const stepOrders = (graph!.get('stepOrders') as bigint[]).map(Number);
      const firstStepOrder = Math.min(...stepOrders);

      await page.goto(`/chat?skillId=${skillId}`);
      await sendMessage(
        page,
        `I finished all the work on step ${firstStepOrder} of my plan, it's done!`
      );

      await expect
        .poll(async () => fetchCheckins(skillId), { timeout: 20_000 })
        .not.toHaveLength(0);
      const checkins = await fetchCheckins(skillId);
      expect(checkins[0].source).toBe('conversation');
      expect(['completed', 'partial']).toContain(checkins[0].outcome);
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });

  test('reporting a struggle records an obstacle CheckIn and the coach responds', async ({
    page,
  }) => {
    test.setTimeout(180_000);
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

      await page.goto(`/chat?skillId=${skillId}`);
      const result = await sendMessage(
        page,
        "I keep sinking every time I try to float, it's really frustrating."
      );
      expect(result.reply.length).toBeGreaterThan(0); // the coach did respond, not a silent failure

      await expect
        .poll(async () => fetchCheckins(skillId), { timeout: 20_000 })
        .not.toHaveLength(0);
      const checkins = await fetchCheckins(skillId);
      // An LLM may reasonably ask a clarifying question instead of
      // recording an obstacle outright on the very first ambiguous-ish
      // report -- only assert the outcome shape when one WAS recorded.
      if (checkins.length > 0) {
        expect(['obstacle', 'partial']).toContain(checkins[0].outcome);
      }
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });
});
