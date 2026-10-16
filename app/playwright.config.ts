import path from 'node:path';

import { defineConfig, devices } from '@playwright/test';
import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, 'e2e/playwright/.env') });

const baseURL = process.env.E2E_BASE_URL ?? 'http://localhost:4021';

/**
 * Runs against the static `expo export --platform web` build (npm run
 * e2e:build/e2e:serve), not the Metro dev server -- that's the shipped
 * artifact, not a dev-loop approximation of it.
 *
 * Port 4021 is deliberately uncommon, not 8081/3000/8000/etc: this machine
 * runs other, unrelated Expo/Metro projects that default to those same
 * ports. A real run once found `reuseExistingServer: true` silently
 * treating an unrelated project's already-running dev server on 8081 as
 * "our" server -- Playwright then tested against, and captured a failure
 * snapshot of, that other app's manifest (which contained live third-party
 * secrets, since it happened to be a different real project). `
 * reuseExistingServer: false` below means a port collision now fails loudly
 * ("port already in use") instead of silently running tests against
 * whatever happens to already be listening.
 *
 * workers: 1 -- specs share two seeded accounts (fixtures/test-users.ts);
 * running them one at a time avoids cross-test races on that shared state.
 */
export default defineConfig({
  testDir: './e2e/playwright/tests',
  globalSetup: './e2e/playwright/global-setup.ts',
  workers: 1,
  reporter: 'list',
  use: {
    baseURL,
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'npm run e2e:serve',
    url: baseURL,
    reuseExistingServer: false,
    timeout: 30_000,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
