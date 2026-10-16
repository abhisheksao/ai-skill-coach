# Tasks: Foundations

**Input**: Design documents from `/specs/001-foundations/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

**Tests**: included — Constitution VIII and contracts/api.md §Contract tests
require them. Write tests before or with the code they cover; they must fail
before the implementation exists.

**Organization**: grouped by user story from spec.md. US1 = auth, US2 = chat,
US3 = profile step + coaching graph.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- Paths are repo-relative; monorepo layout per plan.md

---

## Phase 1: Setup

**Purpose**: two runnable scaffolds and the guardrails around them

- [x] T001 Scaffold `api/`: `uv init`, `pyproject.toml` with fastapi, uvicorn,
      langchain-google-genai, neo4j, pyjwt[crypto], httpx, pydantic-settings,
      supabase, tenacity (dev: ruff, pytest, pytest-asyncio); package skeleton
      `api/src/skillcoach_api/{main,config,auth}.py` + `routes/ services/
      models/ tests/` stubs; app boots with `uv run uvicorn skillcoach_api.main:app`
- [x] T002 Scaffold `app/`: Expo TypeScript template with expo-router;
      `app/app.json` sets `"name": "Skill Coach"`, `"scheme": "skillcoach"`
      (FR-013); install @supabase/supabase-js, expo-secure-store,
      expo-web-browser, expo-auth-session, expo-localization, i18next,
      react-i18next; `npx expo start --web` renders a placeholder screen
- [x] T003 [P] Configure ruff (lint+format) in `api/pyproject.toml`; `uv run
      ruff check .` passes
- [x] T004 [P] Configure ESLint + jest in `app/` (expo defaults); `npm run lint`
      and `npm test` pass locally
- [x] T005 [P] ~~CI workflow~~ **DEFERRED** (2026-07-12): all CI deferred to
      feature 005; api checks run locally (`uv run ruff check . && uv run
      ruff format --check . && uv run pytest`)
- [x] T006 [P] Export `assets/branding/logo.svg` to PNGs (1024 icon, Android
      adaptive foreground, splash) into `app/assets/`; reference in `app.json`

**🛑 CHECKPOINT — HUMAN REVIEW (guardrail from dev plan §6.4)**: stop after
T001–T006 and review scaffolds before proceeding in larger batches.

---

## Phase 2: Foundational (blocks all user stories)

- [x] T007 `api/src/skillcoach_api/config.py`: pydantic-settings for SUPABASE_URL,
      SUPABASE_SERVICE_ROLE_KEY, SUPABASE_JWKS_URL, NEO4J_URI/USER/PASSWORD,
      GOOGLE_API_KEY, LLM_MODEL, DAILY_LLM_BUDGET, CORS_ORIGINS, POLICY_URL;
      commit `api/.env.example` (Constitution VI: model id config-only)
- [x] T008 `supabase/migrations/20260712000001_init.sql` (moved from
      api/migrations/postgres when the Supabase GitHub integration was
      connected, 2026-07-12): `profiles`, `messages`,
      `llm_usage` per data-model.md — RLS policies (client select-own only),
      `(user_id, session_id, created_at)` index, and
      `increment_llm_usage(uid uuid) returns int` SQL function (atomic upsert
      for the budget guard); apply to the Supabase project
- [x] T009 [P] `api/migrations/neo4j/001_init.cypher`: `:User(id)` uniqueness
      constraint; apply to Aura
- [x] T010 `api/src/skillcoach_api/auth.py`: JWKS fetch + TTL cache, Bearer
      verification, `sub` extraction as request principal; 401 error envelope;
      tests `api/tests/test_auth.py` (contract tests 1–2: /health open, garbage/
      expired token → 401)
- [x] T011 `api/src/skillcoach_api/main.py`: app factory, CORS, error-envelope
      exception handlers (`{error: {code, message_key}}`), `routes/health.py`
      (GET /health with git sha); test `api/tests/test_health.py`
- [x] T012 [P] `app/src/lib/supabase.ts`: client with AsyncStorage-backed session
      persistence on native (research R12 — SecureStore's 2KB Android limit) /
      localStorage (web); foreground-only token auto-refresh; typed profile fetch
- [x] T013 [P] `app/src/i18n/`: i18next init from device locale
      (expo-localization) with profile override hook; starter catalogs
      `locales/{en,hi,es,fr,de}.json` covering all 001 UI strings + budget/error
      message keys from contracts/api.md
- [x] T014 [P] `app/src/theme/tokens.ts` from docs/design-theme.md (light+dark)
      + `components/{PrimaryButton,ChatBubble,LoadingDots}.tsx` using tokens only
- [x] T015 `app/app/_layout.tsx`: root providers (theme, i18n) + auth-gate
      routing — signed-out → `(auth)/sign-in`; signed-in without `profiles` row →
      `(onboarding)/profile`; else `(main)/chat`

**Checkpoint**: foundation ready — user stories can begin

---

## Phase 3: User Story 1 — Create an account and sign in (P1) 🎯 MVP

**Goal**: email + Google auth working on iOS/Android/web; sessions persist.

**Independent Test**: spec US1 scenarios 1–4 (sign up, cross-platform sign-in,
restart persistence, bad-credential error).

- [x] T016 [US1] `app/app/(auth)/sign-up.tsx`: email/password signup with
      validation + "account exists" path to sign-in (edge case)
- [x] T017 [US1] `app/app/(auth)/sign-in.tsx`: email/password sign-in, error
      states, link to sign-up
- [x] T018 [US1] Google OAuth: `signInWithOAuth({provider:'google'})` via
      expo-web-browser, redirect `skillcoach://auth-callback` (native) / site URL
      (web); document the Supabase-dashboard provider setup in api/README
- [x] T019 [US1] `app/app/(main)/settings.tsx`: sign-out (clears session, routes
      to sign-in); verify cold-start session restore on device

**Checkpoint**: US1 passes independently on all three platforms

---

## Phase 4: User Story 2 — Exchange a text message with the AI (P2)

**Goal**: `/v1/chat` round trip with persistence, budget guard, localized reply.

**Independent Test**: spec US2 scenarios 1–3 + quickstart scenarios 2, 7, 8.

- [x] T020 [P] [US2] `api/src/skillcoach_api/models/chat.py`: ChatRequest
      (message 1–4000 chars, session_id uuid), ChatResponse, and
      `ChatTurn {reply: str, intents: list = []}` — the fixed envelope
      (002 inherits it)
- [x] T021 [US2] `api/src/skillcoach_api/services/budget.py`: `BudgetGuard.acquire
      (user_id)` calling `increment_llm_usage` RPC; over `DAILY_LLM_BUDGET` →
      `BudgetExceeded`; tests `api/tests/test_budget.py` (contract test 6:
      no LLM call, no rows when over)
- [x] T022 [US2] `api/src/skillcoach_api/services/llm.py`: ChatGoogleGenerativeAI
      + `.with_structured_output(ChatTurn)`, system prompt takes reply-language
      parameter, tenacity backoff (3 attempts on 429/5xx) then `LlmUnavailable`;
      tests with mocked model `api/tests/test_llm.py`
- [x] T023 [US2] `api/src/skillcoach_api/services/messages.py`: service-role
      insert of user+assistant rows (user_id from JWT, session_id, skill_id=null,
      modality='chat' stamped server-side); tests `api/tests/test_messages.py`
- [x] T024 [US2] `api/src/skillcoach_api/routes/chat.py`: POST /v1/chat
      orchestration — auth → budget → LLM → persist → respond; 429
      `budget_exceeded`, 503 `llm_unavailable` with **zero** rows persisted on
      failure (FR-007); contract tests 5–7 in `api/tests/test_chat_contract.py`
- [x] T025 [US2] `app/app/(main)/chat.tsx`: history via Supabase RLS read
      (ordered by created_at), session_id per conversation open, optimistic send
      with pending state, failure keeps draft + retry, 429 rendered as coach
      bubble via message_key
- [x] T026 [US2] (code complete; live EN+HI check pending GOOGLE_API_KEY) Reply language: profile language (fallback device locale
      pre-profile) flows client → API → system prompt; manual check EN + HI
      (Constitution X)

**Checkpoint**: US2 passes; chat works end-to-end on device against local API

---

## Phase 5: User Story 3 — New signups enter the coaching graph (P3)

**Goal**: profile step (language/name/consent) creates `profiles` row +
`(:User)`; reconciliation heals failures.

**Independent Test**: spec US3 scenarios 1–3 + quickstart scenarios 1, 5, 6.

- [x] T027 [P] [US3] `api/src/skillcoach_api/services/graph.py`: async Neo4j
      driver lifecycle + `ensure_user(sub)` MERGE (parameterized, idempotent);
      tests with mocked driver `api/tests/test_graph.py`
- [x] T028 [US3] `api/src/skillcoach_api/routes/profile.py`: POST /v1/profile —
      validate (language enum, IANA timezone, consent must be true → 422),
      service-role upsert `profiles`, then `ensure_user`; 200 even when graph
      write fails (logged; US3 scenario 2); contract tests 3–4 in
      `api/tests/test_profile_contract.py`
- [x] T029 [US3] Wire lazy `ensure_user` into POST /v1/chat (reconciliation
      path); test: chat call heals missing `(:User)` (quickstart scenario 6)
- [x] T030 [US3] `app/app/(onboarding)/profile.tsx`: language picker (5 options,
      device locale pre-selected), optional display-name field, consent checkbox
      linking to `POLICY_URL` page, submit → POST /v1/profile → route to chat;
      i18n switches immediately to chosen language; abandoning re-presents on
      next launch (gate from T015)

**Checkpoint**: all three stories pass independently

---

## Phase 6: Polish & Cross-Cutting

- [x] T031 [P] Cross-tenant scoping test (contract test 8): user A's token can
      never read/write user B's rows/nodes — `api/tests/test_tenancy.py`
      (Constitution I)
- [x] T032 [P] Structured logging in api (request id, user sub, route, LLM
      outcome; never message content or secrets)
- [x] T033 Root `README.md`: bring-up guide (links to quickstart.md) — a
      teammate can run the stack from README alone (SC-004)
- [x] T034 Deploy api/ to Render free tier (render.yaml blueprint, 786666f) —
      verified live (`/health` returns deployed commit sha); device reaches it
      over the internet (no LAN dependency); cold starts accepted per spec
- [x] T035 Quickstart validation run 2026-07-13 (Chrome + physical Android;
      iOS deferred — no device available). Results recorded in
      `specs/001-foundations/quickstart.md`. 8/10 verified live, 1 skipped
      (covered by automated contract test), 1 deferred (iOS-specific device).
      Feature exit gate met on tested platforms (Constitution VIII).

  **⏸ RESUME WHEN AN iOS DEVICE IS AVAILABLE** (tracked in
  `specs/README.md`'s "Deferred: iOS device validation" section):
  - Quickstart #1 (sign-up + profile step) on a physical iPhone — currently
    only covered via the Playwright web variant (`foundations.spec.ts`) and
    physical Android.
  - Quickstart #4 (same account signed in on iOS+Android+web simultaneously)
    — only partially exercised (web+Android at different times, not a
    dedicated concurrent run).
  - `app/.maestro/flows/session-persists.yaml` — written 2026-07-15, never
    run on any device (Android would also satisfy this one, not iOS-only).

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2 → stories**: T001 blocks T003/T005/T007+; T002 blocks
  T004/T006/T012+; T008 blocks T021/T023; T010 blocks T024/T028; T015 blocks
  T025/T030
- **Stories**: US1 first (auth tokens are needed to exercise US2/US3 against a
  real backend). US2 and US3 are independent of each other after Phase 2 —
  T027/T028 can proceed in parallel with T020–T024
- **Within stories**: models → services → routes → app screens; tests with or
  before implementation
- **T034/T035 last** (deploy, then validate everything)

## Implementation Strategy

Per dev-plan §6.4: **implement T001–T006, then stop for human review** (marked
checkpoint above). After sign-off, proceed phase by phase, committing after each
task or logical group. MVP slice = Phases 1–3 (auth working everywhere); US2 and
US3 land next in either order; T035 is the exit gate before feature 002.
