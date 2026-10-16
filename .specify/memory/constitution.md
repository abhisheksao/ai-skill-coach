<!--
Sync Impact Report
- Version change: 1.8.0 → 1.9.0 (MINOR: workflow guidance removed, no
  principle redefined or removed)
- Modified principles: none
- Added sections: none
- Removed sections: none (one bullet removed from "Development Workflow")
- Templates requiring updates: none. Checked plan-template.md,
  tasks-template.md and the command files under .specify/templates/; none
  prescribe a model per stage.
- Follow-up TODOs: none
-->

# Skill Coach Constitution

Voice-first skill-learning coach (swimming, running, chess, …). These principles are
non-negotiable across all features. Source of truth for architecture, schema, and
phasing: `docs/skill-coach-development-plan.md` (Sections 1–5). Where a spec, plan,
or task
contradicts this constitution, the constitution wins.

## Core Principles

### I. LLM Never Writes Cypher (NON-NEGOTIABLE)
All state-mutating action is expressed as typed intents (JSON) validated against
Pydantic schemas. A deterministic backend layer translates validated intents into
parameterized Cypher — this is the **only** path to a write, regardless of where
the intent came from. An intent may be produced by the LLM (parsed from a
conversation turn) or constructed directly by the client for a UI-native action
(e.g., tapping to mark a step complete); a UI-native intent skips the LLM call
entirely — there is no ambiguity to parse for a structured tap — but validates
against the same schema and is applied by the same translator as any
LLM-produced intent. On validation failure, retry with error feedback (max 2
retries; UI-native intents that fail validation surface the error directly, with
no LLM retry to fall back to), then degrade gracefully — never a user-visible
crash, never an unvalidated write. Every applied intent is recorded in an audit
log. The backend authenticates every request by validating the auth provider's
token, and every graph read or write is scoped to the authenticated user's
subgraph — no query may span users.

### II. Progress Is Derived, Never Stored
Progress, streaks, and cadence adherence are always computed from CheckIn nodes at
read time. No mutable progress counters exist anywhere — not in the graph, not in
Postgres, not in client state treated as authoritative.

### III. Goal History Is Immutable
Goal revisions create new Goal nodes linked to their predecessor via `SUPERSEDES`.
Existing Goal nodes are never overwritten or deleted, so the coach can always see the
user's trajectory. No UI path may delete or terminally "end" a goal — a goal stays
open indefinitely as a standing pursuit unless a superseding revision changes it;
ending a pursuit is a product decision the coach discusses in conversation, never a
raw delete button.

### IV. Single Message Pipeline
Voice and chat produce identical message records distinguished only by a `modality`
flag. Nothing downstream of message ingestion (LLM calls, intent handling, graph
writes, summaries) may branch on modality.

### V. All LLM Calls Are Budgeted
Every LLM call goes through a rate-limit queue with per-user daily budgets and
exponential backoff. Cheap calls (summaries, classification) use the lite model tier;
generation (plans, coaching turns) uses the standard tier.

### VI. Provider/Tier Switch Is Config-Only
Moving the LLM provider from free to paid tier, or swapping models, must require zero
code changes — configuration and secrets only.

### VII. Data Placement Rule
Structured coaching state (users, skills, goals, plans, steps, sessions, check-ins)
lives in Neo4j. Transcripts, auth, push tokens, and cadence/notification schedules
live in Supabase Postgres. Raw transcripts never enter the graph.

### VIII. Testing Discipline
Every functional requirement, acceptance scenario, and edge case in a feature's spec
must have a corresponding automated test before that feature is marked complete —
verified by inspection against the spec at each feature's exit gate; no numeric
coverage percentage is enforced in CI. Three categories of automated test are
required, matched to what's being verified:
- **Unit tests** at the function level, explicitly including negative and
  error-path cases (validation failures, malformed input, provider errors) —
  not happy-path only. The intent→Cypher translation layer and the context
  builder are non-negotiable examples.
- **API contract tests** for backend request/response behavior.
- **UX workflow tests** for scenarios that only make sense end-to-end in a
  browser or on a device: Playwright drives the Expo web export, Maestro
  drives the native app. Both run locally or against a connected
  device/emulator — no paid device farm, consistent with Principle IX.

Any scenario validated by hand during development — including live-device
quickstart testing — must be captured as an automated test in one of the
above suites wherever feasible, so later work can be checked against it
automatically instead of relying on a repeat manual pass. This applies
retroactively: features 001 and 002, already implemented, get their existing
manual quickstart scenarios backfilled into Playwright/Maestro suites before
003 begins. Multilingual coverage stays sampled, not multiplied: full
acceptance runs in English and Hindi; Spanish, French, and German get smoke
tests (decision 2026-07-12).

Test generation is never optional and never conditional on being explicitly
requested at invocation time. Every `/speckit.tasks` run for this project
must produce test tasks for every user story phase as a matter of course —
a spec or task-generation template's own "tests are optional unless asked"
default does not override this principle; that gap has previously caused
test tasks to be silently skipped and must not recur. What remains
genuinely optional is *how much of a scenario* gets automated (see the
UX-workflow carve-out below), never *whether it gets a test task at all*.

Every feature must maintain a documented, human-executable regression
catalog at `docs/testing.md`: an index of every automated test (file/name)
mapped to the requirement or scenario it proves, plus a manual checklist for
anything not yet automated (typically live-device or paid-quota-sensitive
scenarios). Update `docs/testing.md` at each feature's exit gate — it is
part of "done," not a follow-up task.

### IX. Cost Ceiling
Development runs at $0/month on free tiers (cold starts accepted). Any deliverable
that would introduce spend must be flagged to the human for approval, never silently
added. The first sanctioned spend is the warm-host + paid-LLM-tier switch in feature
005 (`hardening-and-pilot`).

### X. Multilingual by Default
Users interact with the product — UI, coach conversations (chat and voice, STT and
TTS), and generated content (plans, summaries, notifications) — in their preferred
language. Launch set: English, Hindi, Spanish, French, German (adjustable before
feature 001 planning; extensible later). Language preference lives on the user
profile, defaults to the device locale (falling back to English if unsupported),
and is changeable at any time. No feature may hard-code an English assumption;
adding a supported language must be a configuration/content change, not a code
change.

## Architectural Constraints

- **Graph schema (v1)** — fixed; changes require human approval:

  ```
  (:User)-[:PURSUES]->(:Skill)
  (:Skill)-[:HAS_GOAL]->(:Goal)          // revisions: (:Goal)-[:SUPERSEDES]->(:Goal)
  (:Skill)-[:HAS_PLAN]->(:Plan)-[:HAS_STEP]->(:Step)
  (:Plan)-[:FOR_GOAL]->(:Goal)           // which goal the plan serves (approved 2026-07-12)
  (:Plan)-[:SUPERSEDES]->(:Plan)         // plan revisions; one active (non-superseded) plan per skill
  (:Skill)-[:HAS_SESSION]->(:Session)    // one per conversation; holds LLM summary
  (:Step)<-[:FOR_STEP]-(:CheckIn)        // timestamp, outcome, sentiment, obstacle?,
                                          // source: conversation | ui_tap (approved 2026-07-13)
  ```

- **Intent vocabulary (v1)**: `create_skill`, `create_plan`, `revise_plan`,
  `revise_goal`, `log_checkin`, `report_obstacle`, `complete_step`,
  `summarize_session`. Each has a Pydantic schema. Additions are allowed; renames or
  semantic changes to existing intents require human approval.
- **Stack**: Expo React Native client (dev build; iOS/Android/web),
  FastAPI + LangChain backend, Gemini Flash / Flash-Lite, Neo4j Aura Free,
  Supabase (auth, transcripts, push tokens, cadence, pg_cron, pg_net), expo-notifications,
  expo-speech-recognition + expo-speech (push-to-talk).
- **Skill routing v1**: explicit skill selection in the UI; free-form intent
  classification is deferred to v2.
- Secrets never enter the repo: `.env` locally, host-level secrets in deploys.
- **Design system**: UI colors, typography, and logo follow
  `docs/design-theme.md` (single source of design tokens; provisional — palette
  and logo may be replaced, which must be a token/asset swap only).

## Development Workflow

- Features are implemented one at a time in numbered order (001–005); a feature's
  success criteria must pass before the next feature starts.
- Per feature: specify → clarify → plan → tasks → analyze → implement. Clarify and
  analyze must not be skipped for features 002 and 004.
- Ask the human before: any spend, any change to the v1 graph schema, any new
  third-party service, or deleting data.
- Verify live external limits (LLM quotas, Aura node limits) in their consoles rather
  than trusting snapshots in planning documents.

## Governance

This constitution supersedes all other practices in this repository. Amendments
require documenting the change, bumping the version below, and recording rationale in
the amendment commit. All specs, plans, and code reviews must verify compliance with
the principles above; violations block merge. Complexity beyond what a feature's spec
requires must be justified in its plan.

**Version**: 1.9.0 | **Ratified**: 2026-07-11 | **Last Amended**: 2026-10-12

Amendment 1.9.0 (2026-10-12): Development Workflow drops the per-stage
model-selection bullet added in 1.8.0. User request, 2026-10-12.

Amendment 1.7.1 (2026-07-17): Stack list gains `pg_net` alongside `pg_cron`
— 004's nightly cadence scan and session-summarize poll need `pg_net` for
the cron jobs to make an outbound HTTP call into the FastAPI backend;
`pg_cron` alone can only schedule SQL, not reach an external service.
Same Supabase-bundled-extension category as `pg_cron`, no new vendor or
spend. Surfaced by `/speckit-analyze` during 004 planning, human-approved
2026-07-17.

Amendment 1.7.0 (2026-07-14): Principle VIII closes an opt-in loophole — the
installed `speckit-tasks` skill defaulted to "tests are optional unless
explicitly requested," which is why 001 needed manual intervention to get
test tasks generated at all. Test task generation is now stated as
never-optional and never conditional on being asked for, overriding any
template default (skill itself fixed same day: `.claude/skills/speckit-
tasks/SKILL.md` now generates test tasks by default whenever a Testing
Discipline principle exists). Also adds a standing requirement for a
maintained `docs/testing.md` regression catalog (automated test index +
manual checklist), updated at every feature's exit gate. Prompted by user
request, 2026-07-14.

Amendment 1.6.0 (2026-07-14): Principle VIII rewritten — every FR/acceptance
scenario/edge case needs an automated test (unit, API contract, or UX
workflow), function-level unit tests must cover negative/error paths
explicitly, and UX workflow scenarios get automated coverage via Playwright
(web) and Maestro (app) instead of living only in manual quickstart runs.
Applies retroactively: 001/002 get their manual quickstart scenarios
backfilled before 003 begins. Prompted by live device testing during 002
(user request, 2026-07-14).

Amendment 1.5.0 (2026-07-13): Principle I broadened — intents may originate
from a UI-native action as well as LLM-parsed conversation, both validated
and translated by the same single pipeline. Principle III gains an explicit
no-delete-from-UI rule for goals. Graph schema: `CheckIn` gains a `source`
property (`conversation` | `ui_tap`), approved for feature 004's home
dashboard / direct step-completion capability.

Amendment 1.4.0 (2026-07-12): graph schema gains (:Plan)-[:FOR_GOAL]->(:Goal) and
(:Plan)-[:SUPERSEDES]->(:Plan), human-approved — plans are linked to the goal they
serve, plan revisions keep history, one active plan per skill.

Amendment 1.3.0 (2026-07-12): Principle VIII gains the multilingual test-sampling
policy (full acceptance EN+HI, smoke ES/FR/DE).

Amendment 1.2.0 (2026-07-12): Principle I extended with request authentication and
per-user graph scoping (tenant isolation), from the pre-plan gap review.

Amendment 1.1.0 (2026-07-12): added Principle X (Multilingual by Default — launch
languages EN/HI/ES/FR/DE) and the design-system constraint pointing at
`docs/design-theme.md`, per product-owner direction.
