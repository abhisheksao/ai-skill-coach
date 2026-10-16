# Data Model — 001 Foundations

Phase 1 output. Placement rules per Constitution VII.

## Supabase Postgres

### `profiles`

One row per user, created at profile-step completion (FR-006/FR-010/FR-011/FR-012).

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `user_id` | uuid | PK, FK → `auth.users(id)` on delete cascade | Supabase auth identity |
| `display_name` | text | nullable | optional (FR-010) |
| `language` | text | not null, check in (`en`,`hi`,`es`,`fr`,`de`) | explicit picker (FR-011) |
| `timezone` | text | not null | IANA name, auto-detected (FR-010) |
| `consent_at` | timestamptz | not null | consent checkbox timestamp (FR-012) |
| `created_at` | timestamptz | not null default now() | |
| `updated_at` | timestamptz | not null default now() | |

RLS: select/update own row (`user_id = auth.uid()`); insert via API (service
role) only — the API is what also creates `(:User)`.

### `messages`

Append-only transcript store (FR-005). Never mirrored to the graph.

| Column | Type | Constraints | Notes |
|---|---|---|---|
| `id` | uuid | PK default gen_random_uuid() | |
| `user_id` | uuid | not null, FK → `auth.users(id)` | tenant key |
| `session_id` | uuid | not null | groups a conversation; client-generated per conversation open; no graph counterpart until 004 |
| `skill_id` | uuid | nullable | null until feature 002 |
| `sender` | text | not null, check in (`user`,`assistant`) | |
| `content` | text | not null | user-confirmed text only |
| `modality` | text | not null default `chat`, check in (`chat`,`voice`) | `voice` unused until 003 (Constitution IV) |
| `created_at` | timestamptz | not null default now() | |

Index: `(user_id, session_id, created_at)`.
RLS: select own rows; **no** insert/update/delete for clients — API service role
writes (research R9).

### `llm_usage`

v0 budget guard (FR-009, Constitution V).

| Column | Type | Constraints |
|---|---|---|
| `user_id` | uuid | not null |
| `usage_date` | date | not null |
| `count` | int | not null default 0 |
| | | PK (`user_id`, `usage_date`) |

Increment atomically: `INSERT … ON CONFLICT (user_id, usage_date) DO UPDATE SET
count = llm_usage.count + 1 RETURNING count`. No client access (service role
only).

## Neo4j (Aura Free)

### `(:User)`

| Property | Type | Notes |
|---|---|---|
| `id` | string (uuid) | = `auth.users.id` / JWT `sub`; unique constraint |
| `created_at` | datetime | set on create |

Migration: `CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE
u.id IS UNIQUE;`

Write path: `MERGE (u:User {id: $sub}) ON CREATE SET u.created_at = datetime()`
— parameterized, idempotent, invoked at profile completion and lazily on `/chat`
(reconciliation). No other labels/relationships in 001; the 002 schema
(Skill/Goal/Plan/Step, constitution v1.4.0) attaches to this node.

## Client-side (not persisted)

- **Draft message**: kept in component state until the API confirms; survives a
  failed send (FR-007).
- **Session id**: generated (uuid v4) when the chat screen opens with no active
  session; regenerated per app cold start in 001 (session semantics tighten
  in 004).
- **Pre-profile language**: device locale via expo-localization; replaced by
  `profiles.language` after the profile step.

## Invariants

1. A `profiles` row and a `(:User)` node exist together after profile-step
   completion; the lazy `ensure_user` path heals a missing node — never a
   missing profile row (profiles is written first, transactionally).
2. Every `messages` row belongs to the JWT `sub` that produced it; no
   cross-user reads (RLS) or writes (service role stamps `user_id` from the
   verified token, Constitution I).
3. `modality` is stamped server-side; clients cannot set it.
