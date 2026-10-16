# Skill Coach API

FastAPI backend. Validation guides: `specs/001-foundations/quickstart.md`
(auth/profile/chat), `specs/002-wizard-and-plan/quickstart.md` (wizard,
plan generation, regeneration), `specs/003-voice-layer/quickstart.md`
(push-to-talk, spoken replies), and
`specs/004-progress-and-notifications/quickstart.md` (check-ins, cadence
nudges, dashboard, session continuity).

## Endpoints

| Method & path | Feature | Notes |
|---|---|---|
| `GET /health` | 001 | unauthenticated |
| `POST /v1/profile` | 001, extended 003 | post-signup language/name/consent; `voice_replies_enabled` (003, default `true`) |
| `POST /v1/chat` | 001, extended 002, 003, 004 | single message pipeline; `skill_id`/`new_skill_name` drive wizard vs. ongoing-conversation mode; `modality` (`"chat"` \| `"voice"`, default `"chat"`, 003) is stamped on the persisted message only — no other service call ever receives it (Constitution IV); `intents` can now also include `log_checkin`/`report_obstacle`/`complete_step` (004), no shape change |
| `GET /v1/skills` | 002 | caller's skills as cards |
| `GET /v1/skills/{id}` | 002 | goal + active plan + steps; 404 never distinguishes not-found from not-owned |
| `POST /v1/skills/{id}/plan/regenerate` | 002 | reason-driven plan regeneration; 409 `regeneration_cap_reached` at 3 attempts, no LLM call spent |
| `GET /v1/skills/{id}/progress` | 004 | completed steps, streak, per-step cadence adherence — recomputed from `CheckIn`s on every call, never cached (Constitution II) |
| `GET /v1/dashboard` | 004 | one card per skill (goal/plan/progress + staleness flag + per-step list); composes the exact same `ProgressService` call the endpoint above uses (SC-006) |
| `POST /v1/intents/apply` | 004 | UI-native tap-to-complete/log-partial — `complete_step`/`log_checkin` only, validated + applied through the same pipeline as a conversational intent, zero LLM/budget call (SC-007) |
| `POST`/`DELETE /v1/push-tokens` | 004 | managed push-token lifecycle (register upserts on `(user_id, token)`, covers rotation too; revoke is idempotent) |
| `POST /v1/internal/notifications/scan` | 004 | **internal** — `X-Internal-Secret` header, not a user JWT; triggered nightly by a Supabase `pg_cron` job via `pg_net` (see Migrations below) |
| `POST /v1/internal/sessions/summarize` | 004 | **internal** — same auth as above; triggered by a separate `pg_cron` job on a ~15-minute cadence |

Full request/response shapes: `specs/001-foundations/contracts/api.md`,
`specs/002-wizard-and-plan/contracts/api.md`,
`specs/003-voice-layer/contracts/api.md`, and
`specs/004-progress-and-notifications/contracts/api.md`.

**Tunable thresholds** (004): every numeric threshold this feature
introduces — cadence-behind multiplier, notification frequency caps and
quiet hours, stale-goal window, session-inactivity timeout, session-
summary count — lives in `src/skillcoach_api/constants.py`, one named
constant per value, imported everywhere it's used. Deliberately code
constants, not `Settings`/env vars: these are rare-to-change product
tuning values reviewed in a PR, not secrets or per-deploy config
(Constitution VI governs the provider/tier `Settings` fields; this is a
separate category).

**Internal cron endpoints** (004): `/v1/internal/notifications/scan` and
`/v1/internal/sessions/summarize` have no authenticated user — there's no
JWT for a `pg_cron` trigger to present. Both are gated by
`internal_auth.RequireInternalSecret`, which checks the `X-Internal-Secret`
header against `Settings.internal_secret` (fails closed when
unconfigured). The Supabase-side wiring (one `pg_cron` schedule per
endpoint, each calling `net.http_post` via the `pg_net` extension to reach
this API) is set up directly in the Supabase SQL editor/dashboard — it is
not part of this repo's migrations, since it targets this API's live
deployed URL rather than schema. **Verify `pg_cron`/`pg_net` are actually
enabled on this Supabase project's tier in the console before relying on
either job** (research.md R1) — not yet confirmed as of 004's
implementation.

**Tenant scoping note**: every mutating operation is scoped to the
authenticated JWT's `sub`, and — as of feature 002 — every skill-scoped
operation (`revise_plan`/`revise_goal`, and `create_plan`'s pairing with its
`create_skill`) is scoped by the skill's **id**, never by name. Two skills
can share a name (the duplicate-name warning in the app is dismissible, not
a hard block), so a name-based match would be ambiguous — see
`services/intent_apply.py`'s module docstring for the full rationale, and
`tests/test_skill_isolation.py` for the regression test.

## Run locally

```bash
cp .env.example .env   # fill in values (see docs/getting-started.md)
uv sync
uv run uvicorn skillcoach_api.main:app --reload --host 0.0.0.0
```

Checks (no CI yet — run before pushing):

```bash
uv run ruff check . && uv run ruff format --check . && uv run pytest
```

### Running a workflow/feature suite

Every test file carries `pytestmark` markers (registered in `pyproject.toml`,
`--strict-markers` so a typo'd `-m` expression fails loudly instead of
silently running zero tests): one **feature** marker (`foundations` = 001,
`wizard_plan` = 002, `voice_layer` = 003, `progress_notifications` = 004)
plus one or more **domain** markers (`auth`, `chat`, `wizard`, `regenerate`,
`skills`, `profile`, `tenancy`, `models`, `checkins`, `progress`, `cadence`,
`notifications`, `dashboard`, `sessions`, …). Combine them to run just the
slice you care about:

```bash
uv run pytest -m foundations          # everything for feature 001
uv run pytest -m wizard_plan          # everything for feature 002
uv run pytest -m progress_notifications  # feature 004 (+ some shared-file 002 tests)
uv run pytest -m regenerate           # the regenerate flow, wherever it's tested
uv run pytest -m "wizard_plan and skills"   # 002's skills-domain tests only
uv run pytest -m "progress_notifications and notifications"  # just the push-notification tests
```

See the full marker list in `pyproject.toml`'s `[tool.pytest.ini_options]`.

## Migrations

Postgres migrations live in `supabase/migrations/` (repo root) and are applied
automatically by the Supabase GitHub integration on push to main. To apply
manually instead:

```bash
supabase login && supabase link --project-ref <ref> && supabase db push
```

004's migration (`20260717000001_progress_notifications.sql`) adds
`cadence_schedules`/`push_tokens`/`notifications` (all service-role-only,
same posture as `messages`/`llm_usage`) plus the `eligible_sessions_for_
summary(cutoff)` SQL function the session-summarize job's Postgres-side
fan-out uses (PostgREST has no `GROUP BY`/`HAVING`). It does **not**
include the `pg_cron` schedules themselves — see "Internal cron
endpoints" above for why those are set up directly in the Supabase
console instead.

Neo4j (manual until 002 adds tooling):

```bash
cypher-shell -a "$NEO4J_URI" -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" \
  -f migrations/neo4j/001_init.cypher
```

## Supabase dashboard setup (one-time)

1. **Auth → Providers → Email**: enabled by default. For friction-free dev,
   optionally disable "Confirm email".
2. **Auth → Providers → Google** (T018):
   - Create an OAuth client in Google Cloud Console (type: Web application).
   - Authorized redirect URI: `https://<project>.supabase.co/auth/v1/callback`.
   - Paste client ID + secret into the Supabase Google provider form.
3. **Auth → URL Configuration**:
   - Site URL: your web origin (dev: `http://localhost:8081`).
   - Additional redirect URLs: `skillcoach://auth-callback` (native deep link).
4. Copy Project URL / anon key / service-role key / JWKS URL into `app/.env`
   and `api/.env` per the `.env.example` files.
