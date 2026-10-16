import { requireEnv } from '../support/env';

export type TestUser = { email: string; password: string };

export const PW1: TestUser = {
  email: requireEnv('E2E_PW1_EMAIL'),
  password: requireEnv('E2E_PW1_PASSWORD'),
};

export const PW2: TestUser = {
  email: requireEnv('E2E_PW2_EMAIL'),
  password: requireEnv('E2E_PW2_PASSWORD'),
};
