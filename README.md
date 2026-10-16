# AI Skill Coach

A voice-first coach for learning any skill: swimming, running, chess,
programming and more. You tell it what you want to learn. A short wizard
conversation builds a step-by-step plan. The coach then checks in by chat
or voice, tracks progress and nudges you when you fall behind. It
remembers what you talked about last time.

- **Clients:** web and Android (Expo / React Native). iOS builds, but
  isn't covered by the setup guide.
- **Languages:** English, Hindi, Spanish, French and German. These cover
  the UI, the conversation, voice and generated plans.
- **Cost:** runs entirely on free tiers. You bring your own Supabase, Neo4j
  Aura and Gemini accounts.

## Quick start

```bash
git clone <this repo> && cd ai-skill-coach
scripts/bootstrap.sh        # creates env files, then lists what to fill in
# fill in api/.env and app/.env, then:
scripts/bootstrap.sh        # installs deps, pushes DB migrations, sets up Neo4j

cd api && uv run uvicorn skillcoach_api.main:app --reload --host 0.0.0.0
cd app && npx expo start --web
```

The full walkthrough is [docs/getting-started.md](docs/getting-started.md).
It covers which accounts to create and where each value comes from. It
also covers Android, push notifications, deployment and the ops workflows.

## How it works

```
Expo app (web / Android)
  │  Supabase Auth (email, Google)
  ▼
FastAPI backend ──► Gemini (LangChain)       turns are budgeted and rate-limited
  │                    │
  │                    ▼  typed intents (JSON), validated with Pydantic
  │               intent → Cypher translator  the only write path to the graph
  ▼                    ▼
Supabase Postgres    Neo4j Aura
transcripts, push    users → skills → goals → plans → steps,
tokens, schedules,   check-ins, session summaries
budgets, analytics
```

Rules that hold across the codebase
([constitution](.specify/memory/constitution.md)):

- **The LLM never writes Cypher.** The LLM proposes typed intents. A
  deterministic translator validates them and turns them into
  parameterized queries, and every applied intent is audited.
- **Progress is derived, never stored.** Streaks and cadence adherence
  are computed from check-ins when you read them.
- **Goal history is immutable.** A revision supersedes a goal and never
  overwrites it.
- **One message pipeline.** Voice and chat produce identical records,
  told apart only by a `modality` flag.
- **Every LLM call is budgeted.** There's a per-user daily budget, a
  rate-limit queue with backoff, and a kill switch.
- **Switching LLM provider or tier is config only.**

## Repository layout

| Path | What |
|---|---|
| `app/` | Expo app: TypeScript, expo-router |
| `app/packages/core/` | `@ai-skill-coach/core`: reusable client pieces (theme, voice, Supabase/OAuth/API client factories) |
| `api/` | FastAPI backend: Python 3.12, uv |
| `api/packages/coach-core/` | `coach-core`: reusable backend pieces (auth/JWKS, Supabase REST, LLM queue, budget, analytics) |
| `supabase/` | Postgres migrations and the cron-job template |
| `specs/` | Feature specs, plans and task lists, 001–005 ([roadmap](specs/README.md)) |
| `docs/` | [Getting started](docs/getting-started.md) · [testing catalog](docs/testing.md) · [design theme](docs/design-theme.md) · [runbooks](docs/runbooks/) · [original plan](docs/skill-coach-development-plan.md) |
| `scripts/` | `bootstrap.sh` and the Neo4j init helper |

## How it was built

Every feature went through spec-driven development with
[spec-kit](https://github.com/github/spec-kit) and Claude Code:
specify → clarify → plan → tasks → analyze → implement. The
specs, plans, research notes and task lists for features 001–005 are in
`specs/`, alongside the `/speckit-*` skills (`.claude/skills/`) and
templates (`.specify/`) that produced them.

## Checks

```bash
cd api && uv run ruff check . && uv run pytest
cd app && npx tsc --noEmit && npm run lint && npm test
```

## License

[Apache-2.0](LICENSE). See [NOTICE](NOTICE).
