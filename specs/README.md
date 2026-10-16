# Skill Coach: spec roadmap

Each feature here went through [spec-kit](https://github.com/github/spec-kit)'s
flow: specify → clarify → plan → tasks → analyze → implement. The
architecture and phasing came from
[`docs/skill-coach-development-plan.md`](../docs/skill-coach-development-plan.md).
Cross-cutting rules are in the constitution,
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md). Where a
spec and the constitution disagree, the constitution wins.

Specs describe **what** and **why**. Technology choices enter at the
`/speckit-plan` stage.

The feature folders are the working record, kept as written: clarification
logs, research decisions, task lists with their notes, and quickstart
validation results, including the bugs found along the way. Dates and
references to the original deployment are historical.

## Features

| # | Feature | Delivered |
|---|---------|-----------|
| 001 | [Foundations](001-foundations/spec.md) | Expo app (web, Android, iOS dev build) + FastAPI. Supabase auth (email + Google) with a post-signup profile step (language, display name, consent). Budget-guarded Gemini chat with persisted transcripts. A `(:User)` node in Neo4j, healed lazily. |
| 002 | [Wizard & Plan](002-wizard-and-plan/spec.md) | Typed intent vocabulary with Pydantic schemas and an intent → Cypher translator, the only write path. A context builder (profile + active-skill subgraph + transcript). Wizard onboarding that ends in a 3–12 step plan. Regenerate with a reason, capped at 3 attempts. |
| 003 | [Voice Layer](003-voice-layer/spec.md) | Push-to-talk with interim transcripts and an editable transcript before send. Interruptible text-to-speech and a spoken-replies preference. Permission-denial handling and per-language availability checks, with chat as the fallback everywhere. |
| 004 | [Progress & Notifications](004-progress-and-notifications/spec.md) | Conversational and tap-to-complete check-ins. Progress derived from check-ins. A home dashboard. Cadence nudges by push, with a frequency cap and quiet hours. Session summaries for continuity across sessions. Goal revisions that keep history. |
| 005 | [Hardening & Pilot](005-hardening-and-pilot/spec.md) | Rate-limit queue, per-user budgets, a friendly budget-exhausted turn and a kill switch. Nightly graph export + restore. A voice failure matrix. Analytics and structured AI-failure logging. A first-run explainer. Account deletion. Release, deletion and operations runbooks. CI. |

Each folder holds `spec.md`, `plan.md`, `research.md`, `data-model.md`,
`contracts/`, `tasks.md` and `quickstart.md` (manual validation scenarios
and their recorded results). [`docs/testing.md`](../docs/testing.md) maps
every automated test to the requirement it proves.

## Per-feature workflow

For each feature, in order, using the `/speckit-*` skills in
`.claude/skills/`:

1. `/speckit-specify`: what and why, no tech stack.
2. `/speckit-clarify`: resolve the `[NEEDS CLARIFICATION]` markers. The
   answers go into the spec's Clarifications section.
3. `/speckit-plan`: technology choices, research, data model and
   contracts.
4. `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`. Test
   tasks are generated for every user story, never as an opt-in.
5. `/speckit-converge` after implement, repeated until it's clean.
6. The spec's success criteria must pass as acceptance tests, and
   `docs/testing.md` must be updated, before the next feature starts.

## Guardrails

- Ask a human before any spend, any change to the graph schema, any new
  third-party service, or deleting data.
- Check live limits (LLM quotas, Aura node limits) in the providers'
  consoles. Don't trust numbers written in documents.
- Secrets never enter the repo.
- Don't run `/speckit-implement` unattended on a whole task list at
  first. Do a few tasks, review, then take larger batches.

## Known gaps

- **iOS validation**: most device validation ran on Android and Chrome.
  iOS push and Sign in with Apple need a paid Apple Developer account. See
  `docs/testing.md`'s manual checklist and the iOS section of
  [`docs/getting-started.md`](../docs/getting-started.md#ios).
