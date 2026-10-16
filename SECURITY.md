# Security

Please report vulnerabilities privately through GitHub's
**Security → Report a vulnerability** on this repository. Don't open a
public issue.

## Operating your own copy

- Keep `api/.env`, `app/.env`, `google-services.json` and
  `supabase/.temp/` out of git. `.gitignore` already covers them.
- `SUPABASE_SERVICE_ROLE_KEY` bypasses Row Level Security. It belongs
  only on the API host and in GitHub Actions secrets, never in the app.
- `INTERNAL_SECRET` gates the cron-triggered endpoints
  (`/v1/internal/*`). Use a long random value, which
  `scripts/bootstrap.sh` generates for you. Rotate it in the API's env and
  in the Supabase cron jobs together.
- The kill switch and per-user daily budgets cap LLM spend. See
  `docs/runbooks/operations.md`.
