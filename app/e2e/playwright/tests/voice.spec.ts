import { expect, test } from '@playwright/test';

import { PW1 } from '../fixtures/test-users';
import { signInAsUser } from '../support/auth';
import { cleanupSkillsByPrefix, runPrefix } from '../support/cleanup';
import { userIdForEmail } from '../support/db';
import {
  emitError,
  emitFinal,
  emitInterim,
  getTtsCancelCount,
  getTtsSpeakCalls,
  installFakeSpeechRecognition,
  installTtsSpy,
  installUnsupportedBrowser,
  pressMicDown,
  releaseMic,
} from '../support/voice-mock';

/** 003 Voice Layer -- web (Chrome) coverage. Real STT/TTS accuracy is out
 * of scope (see voice-mock.ts); these specs prove the app's *reaction* to
 * recognizer/synthesis events, which is what FR-002/003/004 and SC-004
 * actually specify. Native (iOS/Android) push-to-talk and TTS-interrupt
 * are covered by the .maestro/flows/voice-*.yaml flows instead (device-
 * dependent, see specs/README.md's "Deferred: iOS device validation"). */

test.describe('003 Voice Layer', () => {
  test('push-to-talk: interim renders live, final transcript is editable, sends with modality voice (US1, SC-004)', async ({
    page,
  }) => {
    const prefix = runPrefix();
    const skillName = `${prefix}Voice Test Skill`;
    const userId = await userIdForEmail(PW1.email);

    await installFakeSpeechRecognition(page);
    await signInAsUser(page, PW1);

    try {
      await page.goto('/skills');
      await page.getByRole('button', { name: 'Add skill' }).click();
      await page.getByRole('textbox').fill(skillName);
      await page.getByRole('button', { name: 'Continue' }).click();
      await page.waitForURL('**/wizard**');

      const micButton = page.getByRole('button', { name: 'Speak' });
      await expect(micButton).toBeVisible();

      await pressMicDown(micButton);

      const interimStart = Date.now();
      await emitInterim(page, "I'd like to learn to swim");
      await expect(page.getByText("I'd like to learn to swim")).toBeVisible({ timeout: 1_000 });
      const interimElapsedMs = Date.now() - interimStart;
      // SC-004: interim transcript should render within ~300ms of the
      // recognizer event. This measures the app's own event-to-DOM
      // latency (not real device recognizer latency, which this harness
      // can't produce) -- the app's contribution to the SC-004 budget.
      expect(interimElapsedMs).toBeLessThanOrEqual(300);

      await emitFinal(page, "I'd like to learn to swim", 0.92);
      await releaseMic(page);

      const input = page.getByPlaceholder('Message your coach…');
      await expect(input).toHaveValue("I'd like to learn to swim");

      const [response] = await Promise.all([
        page.waitForResponse(
          (res) => res.url().includes('/v1/chat') && res.request().method() === 'POST',
          { timeout: 30_000 }
        ),
        page.getByRole('button', { name: 'Send' }).click(),
      ]);

      expect(response.status()).toBe(200);
      const requestBody = response.request().postDataJSON() as { modality?: string };
      expect(requestBody.modality).toBe('voice');
    } finally {
      await cleanupSkillsByPrefix(userId, prefix);
    }
  });

  test('low-confidence result shows a confirm hint; edit-before-send still works (US1, FR-003 clarified)', async ({
    page,
  }) => {
    const prefix = runPrefix();
    const skillName = `${prefix}Voice Confidence Skill`;

    await installFakeSpeechRecognition(page);
    await signInAsUser(page, PW1);

    await page.goto('/skills');
    await page.getByRole('button', { name: 'Add skill' }).click();
    await page.getByRole('textbox').fill(skillName);
    await page.getByRole('button', { name: 'Continue' }).click();
    await page.waitForURL('**/wizard**');

    const micButton = page.getByRole('button', { name: 'Speak' });
    await pressMicDown(micButton);
    await emitFinal(page, 'garbled maybe swimming', 0.2); // < 0.5 threshold
    await releaseMic(page);

    await expect(
      page.getByText("We're not sure we got that right — please check before sending.")
    ).toBeVisible();

    // Edit before send still works regardless of the confidence hint.
    const input = page.getByPlaceholder('Message your coach…');
    await input.fill('Definitely swimming');
    await expect(input).toHaveValue('Definitely swimming');
  });

  test('coach reply is auto-spoken when enabled, and a new push-to-talk interrupts it immediately (US2, SC-004)', async ({
    page,
  }) => {
    // Direct navigation to general chat (no skillId) -- chat.tsx's own
    // docstring notes this pre-002 mode is "kept for direct navigation";
    // avoids the cost/complexity of creating a skill just to reach a
    // conversation screen. Settings is reachable from its header.
    await installFakeSpeechRecognition(page);
    await installTtsSpy(page);
    await signInAsUser(page, PW1);

    await page.goto('/chat');
    await expect(page.getByPlaceholder('Message your coach…')).toBeVisible();

    await page.getByPlaceholder('Message your coach…').fill('How is my progress going?');
    await Promise.all([
      page.waitForResponse(
        (res) => res.url().includes('/v1/chat') && res.request().method() === 'POST',
        { timeout: 30_000 }
      ),
      page.getByRole('button', { name: 'Send' }).click(),
    ]);

    // Auto-speak fires once the reply renders.
    await expect(async () => {
      expect(await getTtsSpeakCalls(page)).toHaveLength(1);
    }).toPass({ timeout: 5_000 });

    // Pressing push-to-talk again must cancel any in-progress speech
    // immediately (US2 scenario 2), regardless of whether it's still
    // "speaking" in this headless environment.
    const micButton = page.getByRole('button', { name: 'Speak' });
    const pressStart = Date.now();
    await pressMicDown(micButton);
    await expect(async () => {
      expect(await getTtsCancelCount(page)).toBeGreaterThanOrEqual(1);
    }).toPass({ timeout: 1_000 });
    const cancelElapsedMs = Date.now() - pressStart;
    expect(cancelElapsedMs).toBeLessThanOrEqual(300); // SC-004
    await releaseMic(page);
  });

  test('"Spoken replies" toggle in Settings persists across reload (US2 scenario 3)', async ({
    page,
  }) => {
    // Waits on the actual POST /v1/profile response rather than the
    // "Saved." toast -- US2 scenario 3 requires the setting to persist
    // across reload, which is what's actually asserted below; the toast
    // is a UI nicety, not the acceptance criterion, and proved flaky
    // across two rapid-succession saves in the same test (real timing
    // sensitivity worth avoiding here rather than chasing further).
    async function toggleAndSave(): Promise<void> {
      await Promise.all([
        page.waitForResponse(
          (res) => res.url().includes('/v1/profile') && res.request().method() === 'POST',
          { timeout: 10_000 }
        ),
        page.getByRole('button', { name: 'Save changes' }).click(),
      ]);
    }

    // Real bug found live: this toggle is a custom Pressable, not RNW's
    // native <Switch> -- `accessibilityState={{checked}}` does NOT map to
    // an `aria-checked` DOM attribute for it in this RNW version
    // (confirmed by dumping the actual element: `role="switch"` with no
    // `aria-checked` at all, before or after reload). The "checked" state
    // is only observable via the "✓" glyph rendered as a child of the
    // switch, so check that instead of the (non-existent) attribute.
    const toggle = page.getByRole('switch', { name: 'Spoken replies' });
    async function isToggleOn(): Promise<boolean> {
      return (await toggle.textContent())?.includes('✓') ?? false;
    }

    await signInAsUser(page, PW1);
    await page.goto('/settings');
    await expect(toggle).toBeVisible();

    // Ensure a known starting state (on), independent of prior test runs.
    if (!(await isToggleOn())) {
      await toggle.click();
      await toggleAndSave();
    }

    await toggle.click(); // -> off
    await toggleAndSave();

    await page.reload();
    await expect(page.getByRole('button', { name: 'Save changes' })).toBeVisible();
    await expect(async () => {
      expect(await isToggleOn()).toBe(false);
    }).toPass({ timeout: 10_000 });

    // Leave the shared PW1 account back in its default (on) state.
    await toggle.click();
    await toggleAndSave();
  });

  test('permission denial shows guidance and disables the mic, but chat keeps working (US3)', async ({
    page,
  }) => {
    // On web, expo-speech-recognition's getPermissionsAsync/
    // requestPermissionsAsync are no-ops that always report "granted"
    // (confirmed in the package's own source) -- denial only ever
    // surfaces via the recognizer's `error` event with code
    // "not-allowed", after a start() attempt. Native gets an earlier
    // pre-flight signal instead (see use-voice-session.ts).
    await installFakeSpeechRecognition(page);
    await signInAsUser(page, PW1);

    await page.goto('/chat');
    const micButton = page.getByRole('button', { name: 'Speak' });
    await expect(micButton).toBeVisible();

    await pressMicDown(micButton);
    await emitError(page, 'not-allowed');
    await releaseMic(page);

    await expect(
      page.getByText(
        'Voice is off because microphone access was denied. Enable it in your device settings to use voice.'
      )
    ).toBeVisible();
    await expect(micButton).toHaveAttribute('aria-disabled', 'true');

    // Chat remains fully functional despite the denial.
    const input = page.getByPlaceholder('Message your coach…');
    await input.fill('Still works by text');
    await expect(input).toHaveValue('Still works by text');
  });

  test('unsupported browser: mic control disabled with unavailable guidance, chat fully functional (US4, FR-008)', async ({
    page,
  }) => {
    // Real desktop Chrome (this suite's browser) supports the Web Speech
    // API natively -- installUnsupportedBrowser deletes the globals
    // ExpoSpeechRecognitionModule.web.ts's isRecognitionAvailable() checks,
    // simulating Chrome-on-iOS/Firefox/Safari (research.md R4) without
    // needing a different real browser. This is the SAME
    // resolveMicDisabledReason('unavailable') path T033/T034 already
    // wired for any STT-unavailable case (Android recognizer missing,
    // language unsupported, etc.) -- no separate web-specific code exists
    // or is needed; this test proves that existing wiring also covers the
    // browser-support case FR-008 specifically calls out.
    await installUnsupportedBrowser(page);
    await signInAsUser(page, PW1);

    await page.goto('/chat');
    const micButton = page.getByRole('button', { name: 'Speak' });

    await expect(async () => {
      expect(await micButton.getAttribute('aria-disabled')).toBe('true');
    }).toPass({ timeout: 5_000 });
    await expect(
      page.getByText("Voice isn't available on this device right now. You can keep using chat.")
    ).toBeVisible();

    const input = page.getByPlaceholder('Message your coach…');
    await input.fill('Chat works without voice');
    await expect(input).toHaveValue('Chat works without voice');
  });
});
