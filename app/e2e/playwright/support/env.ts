/**
 * Loads app/e2e/playwright/.env (copy .env.example, gitignored) and fails
 * fast with a clear message if a required var is missing, rather than 40
 * cryptic downstream failures.
 */
import path from 'node:path';

import dotenv from 'dotenv';

dotenv.config({ path: path.resolve(__dirname, '../.env') });

const REQUIRED = [
  'E2E_SUPABASE_URL',
  'E2E_SUPABASE_ANON_KEY',
  'E2E_SUPABASE_SERVICE_ROLE_KEY',
  'E2E_NEO4J_URI',
  'E2E_NEO4J_USER',
  'E2E_NEO4J_PASSWORD',
  'E2E_PW1_EMAIL',
  'E2E_PW1_PASSWORD',
  'E2E_PW2_EMAIL',
  'E2E_PW2_PASSWORD',
  'E2E_API_URL',
] as const;

export function requireEnv(name: (typeof REQUIRED)[number]): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `Missing ${name}. Copy app/e2e/playwright/.env.example to ` +
        `.env and fill in real values (Neo4j creds come from Render's ` +
        `dashboard, not api/.env -- see the example file's comments).`
    );
  }
  return value;
}

export function checkAllRequiredEnvPresent(): void {
  for (const name of REQUIRED) requireEnv(name);
}

export const env = {
  baseUrl: process.env.E2E_BASE_URL ?? 'http://localhost:8081',
  get supabaseUrl() {
    return requireEnv('E2E_SUPABASE_URL');
  },
  get supabaseAnonKey() {
    return requireEnv('E2E_SUPABASE_ANON_KEY');
  },
  get supabaseServiceRoleKey() {
    return requireEnv('E2E_SUPABASE_SERVICE_ROLE_KEY');
  },
  get neo4jUri() {
    return requireEnv('E2E_NEO4J_URI');
  },
  get neo4jUser() {
    return requireEnv('E2E_NEO4J_USER');
  },
  get neo4jPassword() {
    return requireEnv('E2E_NEO4J_PASSWORD');
  },
  get apiUrl() {
    return requireEnv('E2E_API_URL');
  },
};
