# Implementation Plan: Foundations

**Branch**: `001-foundations` | **Date**: 2026-07-12 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-foundations/spec.md`

## Summary

Deliver the authenticated round trip: a user signs up (email/password or Google) on
iOS, Android, or web; completes a post-signup profile step (language picker,
optional display name, consent checkbox) which creates their `(:User)` node in
Neo4j; then exchanges text messages with an AI coach (Gemini Flash-Lite via
LangChain) through a single non-streaming `/chat` endpoint. Messages persist in
Supabase with session/skill/modality attributes from day one. Everything runs on
free tiers ($0/mo), with a v0 per-user LLM budget guard.

## Technical Context

**Language/Version**: TypeScript 5.x (app, Expo SDK current stable at
implementation time, React Native); Python 3.12 (api)

**Primary Dependencies**: app — Expo (dev-build workflow, no EAS), expo-router
(file routing + `skillcoach://` scheme), `@supabase/supabase-js` (auth + reads),
expo-web-browser + expo-auth-session (Google OAuth flow), i18next +
expo-localization (5 launch languages), expo-secure-store (token storage).
api — FastAPI, LangChain (`langchain-google-genai`), `neo4j` Python driver,
PyJWT (Supabase JWKS verification), `httpx`, `pydantic` v2, `uv` for env/deps.

**Storage**: Supabase Postgres (`profiles`, `messages`, `llm_usage`; RLS on) —
auth, transcripts, budget counter. Neo4j Aura Free — `(:User)` only in this
feature. Raw transcripts never enter the graph (Constitution VII).

**Testing**: api — pytest (+ pytest-asyncio, httpx test client). app — ESLint +
jest (unit). All checks run locally; CI deferred to feature 005 (decisions
2026-07-12).

**Target Platform**: iOS (physical device, free provisioning — 7-day expiry
accepted), Android (physical device), web (Chrome desktop) — all from one Expo
codebase. API on Render free tier (cold starts accepted).

**Project Type**: mobile-app + web-service (monorepo: `app/` + `api/`)

**Performance Goals**: none formal in this phase; cold start 30–60 s tolerated
(Constitution IX); warm `/chat` reply within a visible loading state.

**Constraints**: $0/mo total; non-streaming chat (decision 2026-07-12); LLM calls
gated by v0 per-user daily counter + exponential backoff; all UI strings +
LLM replies in EN/HI/ES/FR/DE (Constitution X).

**Scale/Scope**: 1–10 dev users; ~6 screens (sign-in, sign-up, profile step, chat,
settings-lite, policy webview); 3 API endpoints; 3 Postgres tables; 1 node label.

## Constitution Check

*GATE: evaluated against constitution v1.4.0 — re-checked after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| I | LLM never writes Cypher; auth + tenant scoping | PASS | 001 applies no intents (echo returns `intents: []`); structure `{reply, intents[]}` is in the contract from day one. API verifies Supabase JWT on every route; the only Cypher (User upsert) is parameterized and scoped to the token's `sub`. |
| II | Progress derived | N/A | No progress concepts in 001. |
| III | Goal history immutable | N/A | No goals in 001. |
| IV | Single message pipeline | PASS | One `/chat` endpoint; `modality` column written as `chat`; nothing branches on it. |
| V | Budgeted LLM calls | PASS | v0 guard: `llm_usage` daily counter checked before each call + tenacity backoff on 429/5xx; interface designed to be swapped for the 005 queue without touching call sites. |
| VI | Provider/tier config-only | PASS | Model id, API key, temperature in env/config; no model names in code. |
| VII | Data placement | PASS | Auth/transcripts/profile in Supabase; `(:User)` in Neo4j; no transcript content in graph. |
| VIII | Testing | PASS | pytest covers JWT middleware, budget guard, profile→User upsert (intent→Cypher precursor), chat pipeline with mocked LLM; acceptance tests map to SC-001..005. EN+HI full, ES/FR/DE smoke. |
| IX | Cost ceiling | PASS | Render free + Supabase free + Aura free + Gemini free tier; Apple Developer license and Firebase explicitly deferred to 004 (flagged). |
| X | Multilingual | PASS | i18next string catalogs ×5; language picker at profile step; LLM system prompt instructs reply language from profile. |

No violations → Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/001-foundations/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── api.md           # Phase 1 output — REST contract
└── tasks.md             # Phase 2 output (/speckit-tasks — not yet created)
```

### Source Code (repository root)

```text
app/                          # Expo React Native (TypeScript)
├── app/                      # expo-router file routes
│   ├── (auth)/
│   │   ├── sign-in.tsx
│   │   └── sign-up.tsx
│   ├── (onboarding)/
│   │   └── profile.tsx       # language picker + name + consent
│   ├── (main)/
│   │   ├── chat.tsx
│   │   └── settings.tsx
│   └── _layout.tsx           # auth gate + theme provider
├── src/
│   ├── lib/supabase.ts       # client, session persistence (SecureStore)
│   ├── lib/api.ts            # typed client for api/ endpoints
│   ├── i18n/                 # i18next setup + locales/{en,hi,es,fr,de}.json
│   ├── theme/tokens.ts       # from docs/design-theme.md
│   └── components/           # ChatBubble, PrimaryButton, …
├── app.json                  # scheme: "skillcoach", icon from assets/branding
└── package.json

api/                          # FastAPI (Python 3.12, uv)
├── src/skillcoach_api/
│   ├── main.py               # app factory, routers, CORS
│   ├── config.py             # pydantic-settings; model id, keys, URLs
│   ├── auth.py               # Supabase JWKS verification middleware
│   ├── routes/
│   │   ├── health.py         # GET /health
│   │   ├── profile.py        # POST /v1/profile
│   │   └── chat.py           # POST /v1/chat
│   ├── services/
│   │   ├── llm.py            # LangChain → Gemini; {reply, intents[]} schema
│   │   ├── budget.py         # v0 guard (counter + backoff)
│   │   ├── graph.py          # Neo4j driver, ensure_user (parameterized)
│   │   └── messages.py       # persist messages (service-role Supabase)
│   └── models/               # pydantic request/response + intents envelope
├── tests/
├── migrations/
│   ├── postgres/001_init.sql # profiles, messages, llm_usage + RLS
│   └── neo4j/001_init.cypher # constraints
└── pyproject.toml
```

(No CI workflows — all checks local until feature 005.)

**Structure Decision**: Monorepo (decision 2026-07-12) — `app/` and `api/` beside
`specs/` and `docs/`. Mobile + web from the single Expo codebase via
react-native-web; no separate frontend project. CI exists for `api/` only.

## Implementation Notes (how the pieces connect)

1. **Auth flow**: app signs in via supabase-js (email/password) or
   `signInWithOAuth(google)` through expo-web-browser with redirect
   `skillcoach://auth-callback`. Session tokens persist in SecureStore (native) /
   localStorage (web). Every api/ call sends `Authorization: Bearer <access_token>`.
2. **Profile step gate**: after auth, the app checks `profiles` for the user's row;
   missing → route to `(onboarding)/profile`; submitting calls `POST /v1/profile`,
   which upserts the `profiles` row **and** `MERGE`s `(:User {id})` in Neo4j
   (idempotent — safe on retry; FR-006). `/chat` middleware re-runs `ensure_user`
   lazily as the reconciliation path.
3. **Chat pipeline**: `POST /v1/chat` → JWT verified → budget guard → LangChain
   structured output `{reply, intents[]}` (intents ignored-but-logged in 001) →
   persist user message + reply in `messages` (session_id, skill_id=null,
   modality=chat) → return reply. Client renders optimistically with a pending
   state; failures leave the draft intact (FR-007).
4. **Reads**: the app reads message history directly from Supabase under RLS
   (own rows only); the API is the only writer (service role). This keeps the API
   surface to three endpoints.
5. **i18n**: device locale → i18next at first launch; profile language overrides
   after the profile step; the same profile value is injected into the LLM system
   prompt ("reply in {language}").
6. **Budget guard v0**: `llm_usage(user_id, date, count)` upsert-increment before
   the call; over limit → 429 with localized-message key; client renders it as a
   coach bubble. Interface: `BudgetGuard.acquire(user_id)` — the 005 queue replaces
   the implementation, not the call sites.

## Complexity Tracking

No constitution violations — table intentionally empty.
