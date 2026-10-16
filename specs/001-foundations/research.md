# Research — 001 Foundations

Phase 0 output. Format per spec-kit: Decision / Rationale / Alternatives.
All spec-level unknowns were resolved during clarify (2026-07-12); items below are
the technology-selection decisions the plan depends on.

## R1. Expo workflow without EAS

- **Decision**: `npx expo prebuild` + local native builds (Xcode / Android
  Studio); `npx expo run:ios|android` for dev builds; Metro dev server for web.
- **Rationale**: "No EAS, no app CI" decision (2026-07-12); keeps builds free and
  local. Free Apple provisioning signs iOS dev builds (7-day expiry accepted).
- **Alternatives**: EAS Build free tier (rejected: quota-limited, external
  dependency the owner explicitly declined); Expo Go (rejected: won't support
  the native modules arriving in 003/004 — dev-build habit starts now).

## R2. Routing & deep-link scheme

- **Decision**: expo-router (file-based), `"scheme": "skillcoach"` in `app.json`
  from the first scaffold commit.
- **Rationale**: expo-router turns the URL scheme into screen routes for free —
  when 004 needs `skillcoach://skill/{id}/session`, it's a file path, not a
  routing rewrite. Scheme is baked into native builds; reserving it now is
  FR-013.
- **Alternatives**: react-navigation manual linking config (more boilerplate,
  same result); defer scheme to 004 (rejected in gap review — rebuild churn).

## R3. Google OAuth on Expo + Supabase

- **Decision**: `supabase.auth.signInWithOAuth({ provider: 'google' })` opened via
  expo-web-browser, redirect to `skillcoach://auth-callback` (web: site URL).
- **Rationale**: one auth SDK (supabase-js) across all three platforms; no
  native Google SDK, no Firebase involvement; works in dev builds.
- **Alternatives**: `@react-native-google-signin` native flow (faster UX but adds
  a native dependency + Google console SHA-1 management; revisit if the browser
  hop annoys pilot users); Firebase Auth (rejected — decision 2026-07-12,
  Supabase Auth stands).

## R4. Supabase JWT verification in FastAPI

- **Decision**: verify `Authorization: Bearer` tokens with PyJWT against the
  project's JWKS endpoint (`/auth/v1/.well-known/jwks.json`), keys cached
  in-process with TTL; `sub` claim = user id used for all scoping
  (Constitution I).
- **Rationale**: stateless, no per-request Supabase round trip, supports
  Supabase's current asymmetric signing; key rotation handled by JWKS refetch.
- **Alternatives**: legacy HS256 shared-secret verification (works but ties us to
  the legacy secret; use only if the project turns out to be HS256);
  `supabase.auth.get_user()` per request (adds latency + a dependency on Supabase
  uptime per call).

## R5. LLM integration

- **Decision**: `langchain-google-genai` `ChatGoogleGenerativeAI` with
  `.with_structured_output(ChatTurn)` where `ChatTurn = {reply: str, intents:
  list[Intent] = []}`; model id from env (`LLM_MODEL`, default the current
  Flash-Lite alias); temperature/config in `config.py`.
- **Rationale**: locks the option-A single-call contract (decision 2026-07-12)
  into the code shape from the first endpoint; Constitution VI honored by keeping
  model identity in config; 001 uses Flash-Lite (echo-grade traffic).
- **Alternatives**: raw `google-genai` SDK (fewer layers but re-implements
  structured-output plumbing LangChain already provides, and the plan doc
  standardizes on LangChain).

## R6. v0 budget guard

- **Decision**: `llm_usage(user_id, usage_date, count)` in Postgres; atomic
  `INSERT … ON CONFLICT … SET count = count + 1 RETURNING count` before each LLM
  call; over `DAILY_LLM_BUDGET` (env, default 50) → 429 with error code
  `budget_exceeded`. Retries: tenacity exponential backoff (3 attempts) on
  provider 429/5xx.
- **Rationale**: single SQL statement gives atomicity without a queue; the
  `BudgetGuard` interface is what 005's real queue will re-implement.
- **Alternatives**: in-memory counter (rejected: resets on every cold start —
  free-tier hosts restart constantly); Redis (rejected: new service, violates
  cost ceiling spirit).

## R7. API hosting

- **Decision**: Render free tier web service, `uv`-based build, health check on
  `/health`; secrets via Render dashboard env vars.
- **Rationale**: plan doc's default; free; cold starts accepted until 005.
- **Alternatives**: Railway/Fly free allowances (comparable; Render chosen for
  simplest Python story — swap is trivial pre-005); Supabase Edge Functions
  (rejected: Deno/TS runtime, but the API is Python/LangChain).

## R8. i18n library

- **Decision**: i18next + react-i18next + expo-localization; JSON catalogs
  `locales/{en,hi,es,fr,de}.json`; language state = profile value once set,
  device locale before.
- **Rationale**: mature RN support, lazy namespaces later, plural/interpolation
  rules cover HI properly; expo-localization supplies device locale + timezone
  (FR-010's auto-capture) in one dependency. No RTL needed for launch set.
- **Alternatives**: react-intl (heavier ICU tooling for no current need);
  Lingui (nice extraction but adds a compile step to a small app).

## R9. Message reads & writes split

- **Decision**: API (service role) is the only writer to `messages`; the app
  reads history directly from Supabase under RLS (`user_id = auth.uid()`).
- **Rationale**: writing stays in the single pipeline (Constitution IV) where
  session/skill/modality are stamped server-side; reading via RLS avoids a
  paginated list endpoint and keeps the API at three routes.
- **Alternatives**: API-mediated reads (more control, more code — add later if
  context assembly needs it); client-direct writes (rejected: bypasses the
  pipeline and lets clients forge modality/session values).

## R10. Neo4j driver & user upsert

- **Decision**: official `neo4j` async Python driver; single
  `MERGE (u:User {id: $sub}) ON CREATE SET u.created_at = datetime()` in
  `graph.py`; uniqueness constraint on `:User(id)` in `migrations/neo4j/`.
  Called at profile-step completion and lazily from `/chat` (reconciliation,
  FR-006).
- **Rationale**: MERGE + constraint = idempotency guaranteed by the database, not
  application logic; survives Aura Free auto-pause failures via the lazy retry
  path.
- **Alternatives**: neomodel OGM (rejected: the intent→Cypher layer in 002 wants
  hand-written parameterized Cypher, not an ORM's).

## R12. Session storage: AsyncStorage, not SecureStore (amended during T012)

- **Decision**: persist Supabase sessions with
  `@react-native-async-storage/async-storage` (Supabase's official Expo
  guidance); expo-secure-store stays installed for future small secrets.
- **Rationale**: Supabase session JSON (access token + user object) routinely
  exceeds expo-secure-store's 2048-byte Android value limit — sessions would
  silently fail to persist on some devices. Tokens are short-lived JWTs;
  encrypted-at-rest storage (e.g. AES key in SecureStore + ciphertext in
  AsyncStorage) is a feature-005 hardening item.
- **Alternatives**: SecureStore directly (rejected: size limit); LargeSecureStore
  AES pattern (deferred to 005: two more dependencies for a dev-phase app).

## R11. Monorepo tooling

- **Decision**: no workspace manager — `app/` (npm) and `api/` (uv) are
  independent; one `.github/workflows/api-ci.yml` with `paths: [api/**]`
  (ruff + pytest).
- **Rationale**: the two stacks share no code; workspace tooling would add
  ceremony for zero reuse. App lint/tests run locally by decision.
- **Alternatives**: Nx/Turborepo (rejected: single-developer monorepo with two
  disjoint toolchains gains nothing).
