/**
 * Deterministic failure/delay injection via request interception, rather
 * than literal airplane mode -- used for the "kill API mid-send, draft
 * preserved, retry succeeds" scenario (001 quickstart #8).
 */
import type { Page } from '@playwright/test';

export async function breakEndpoint(page: Page, urlGlob: string): Promise<() => Promise<void>> {
  await page.route(urlGlob, (route) => route.abort('failed'));
  return () => page.unroute(urlGlob);
}

export async function delayEndpoint(
  page: Page,
  urlGlob: string,
  delayMs: number
): Promise<() => Promise<void>> {
  await page.route(urlGlob, async (route) => {
    await new Promise((resolve) => setTimeout(resolve, delayMs));
    await route.continue();
  });
  return () => page.unroute(urlGlob);
}
