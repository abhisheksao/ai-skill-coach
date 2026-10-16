import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';

/** 005 US3 -- the web-drivable cells of the R9 voice/chat failure matrix
 * not already covered by 003's voice.spec.ts (V1 permission denial, V3
 * unsupported browser are proven there and deliberately not repeated
 * here). V4: offline compose -> reconnect -> auto-send.
 *
 * Combines real browser-context offline emulation (so NetInfo sees a
 * genuine connectivity transition, driving the auto-retry-on-reconnect
 * path) with a routed abort of POST /v1/chat specifically -- found live
 * that context.setOffline() alone lets an in-flight request to a real
 * external host (vs. same-origin/already-warm connections) hang for a
 * long time rather than failing fast, which isn't what this test is
 * about. The route abort makes the failure deterministic and fast. */
test.describe('005 User Story 3 - Voice/chat failure matrix (web cells)', () => {
  test('V4: offline send keeps the message, marks it failed with retry, and auto-sends once reconnected', async ({
    page,
    context,
  }) => {
    test.setTimeout(60_000);
    await signInAsUser(page, PW1);
    await page.goto('/chat');

    const input = page.getByPlaceholder('Message your coach…');
    await expect(input).toBeVisible();

    await page.route('**/v1/chat', (route) => route.abort('internetdisconnected'));
    await context.setOffline(true);
    await input.fill('Offline test message');
    await page.getByRole('button', { name: 'Send' }).click();

    // Composer never disabled; the message is preserved with a retry
    // affordance instead of silently vanishing.
    await expect(page.getByText('Offline test message')).toBeVisible();
    await expect(page.getByText('Not sent')).toBeVisible();
    await expect(input).toBeEnabled();

    await page.unroute('**/v1/chat');
    await context.setOffline(false);

    // Auto-retry on reconnect -- the failed marker clears once a real
    // reply comes back, no manual tap needed.
    await expect(page.getByText('Not sent')).not.toBeVisible({ timeout: 20_000 });
  });
});
