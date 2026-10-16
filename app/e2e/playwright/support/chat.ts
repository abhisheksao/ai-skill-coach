import type { Page } from '@playwright/test';

export type ChatTurnResult = {
  reply: string;
  session_id: string;
  skill_id: string | null;
  intents: unknown[];
  suggested_replies: string[];
};

/** Types into the chat/wizard input and clicks Send, resolving with the
 * real /v1/chat JSON response -- reading the network response directly is
 * far more robust than parsing rendered chat bubbles (which have no
 * distinguishing testID/role between user and assistant messages). */
export async function sendMessage(page: Page, text: string): Promise<ChatTurnResult> {
  const [response] = await Promise.all([
    page.waitForResponse(
      (res) => res.url().includes('/v1/chat') && res.request().method() === 'POST',
      { timeout: 30_000 }
    ),
    (async () => {
      const input = page.getByPlaceholder('Message your coach…');
      await input.fill(text);
      await page.getByRole('button', { name: 'Send' }).click();
    })(),
  ]);
  return response.json();
}
