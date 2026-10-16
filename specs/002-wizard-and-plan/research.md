# Research — 002 Wizard & Plan Generation

Phase 0 output. All spec-level ambiguity was resolved during clarify
(2026-07-13). These are the technology/design decisions the plan depends on,
several of which resolve mechanics the spec deliberately left as "how."

## R1. Wizard state is reconstructed, never stored

- **Decision**: no `wizard_state`/draft-intake table or intent. Each
  `/v1/chat` call's context includes the last ~20 messages for that
  `session_id` (already persisted by 001 regardless of skill); the LLM
  infers which of the four topics remain from that transcript. The 12-turn
  cap (FR-010) is enforced by counting existing `messages` rows for the
  session server-side — no new counter.
- **Rationale**: FR-004 requires intake data to be transient and *never
  persisted server-side*. Since 001 already persists every message
  regardless of skill, re-reading that transcript is free — no new storage,
  no new intent, no conflict with the "intake is ephemeral" requirement.
- **Alternatives**: a `wizard_draft` intent that the LLM updates each turn
  (rejected — the constitution's intent vocabulary is fixed, additions need
  approval, and this intent would have no Cypher effect, breaking the
  translator's "every intent produces a write" assumption); client-sent
  draft object each turn (rejected — adds a payload shape with no
  correctness benefit over just re-reading the transcript).

## R2. Skill name entry is explicit UI, not conversational

- **Decision**: starting a new skill is a plain text-field entry (FR-001:
  "explicit selection/entry"), checked client-side against `GET /v1/skills`
  for duplicates (fuzzy, case-insensitive) before the wizard conversation
  even opens. The name is sent verbatim as `new_skill_name` on the first
  `/v1/chat` call and used as-is when `create_skill` is applied — never
  re-derived from the LLM's phrasing.
- **Rationale**: zero LLM cost for FR-012's duplicate check; avoids the LLM
  mis-transcribing a name the user already typed correctly.
- **Alternatives**: fully conversational name capture ("what do you want to
  learn?") — rejected, adds an LLM round trip and transcription risk for
  data the UI can just collect directly.

## R3. Accept is a no-op; the plan is written at intake confirmation

- **Decision**: `create_plan` (bundled with `create_skill`) fires the moment
  the user confirms the four-fact intake — not when they later tap "Accept"
  on the review screen. The review screen reads the already-persisted plan
  via `GET /v1/skills/{id}`. Accept is client-side navigation only.
- **Rationale**: FR-007 requires the review screen to render *recorded*
  state, not raw LLM output — write-then-read satisfies this directly.
  Deferring the write until "Accept" would require holding an unpersisted
  draft plan somewhere, reintroducing the server-state problem R1 avoids.
- **Alternatives**: write only on Accept, treat regenerate as operating on
  an in-memory draft (rejected — recreates exactly the ephemeral-state
  problem the constitution's data-placement rule is designed to avoid, and
  complicates the atomicity story for zero benefit).

## R4. Regeneration is a dedicated endpoint, not a chat message

- **Decision**: `POST /v1/skills/{id}/plan/regenerate` with
  `{reason, note?}`, distinct from `/v1/chat`.
- **Rationale**: regeneration needs structured, enforced attempt-counting
  (FR-011's cap of 3) and a fixed reason enum — a dedicated route makes both
  server-side guarantees rather than trusting free-text parsing. It still
  produces a coach-toned reply via the same `{reply, intents[]}` shape
  (option A, decided 2026-07-12), just with a regeneration-specific system
  prompt — no new LLM integration pattern.
- **Alternatives**: encode regeneration as a specially-formatted chat
  message (rejected — pushes structured-input validation into free text for
  no benefit) or a generic PATCH on the plan resource (rejected — the
  reason/attempt-cap semantics are specific enough to deserve their own
  verb).

## R5. Regeneration attempt count is derived from the graph, not stored

- **Decision**: "how many times has this plan been regenerated" = the
  length of the active Plan's `SUPERSEDES` chain back to the original
  `create_plan`-produced Plan for this intake. No counter column/table.
- **Rationale**: consistent with Constitution II's derive-don't-store
  spirit (applied here to plan generations, not just CheckIn-derived
  progress); the graph already models plan history via `SUPERSEDES`
  (constitution v1.4.0), so counting hops is a normal traversal, not new
  schema.
- **Alternatives**: a `regeneration_count` property on Plan (rejected —
  redundant with information the graph already encodes; would need to be
  kept in sync manually, a drift risk the constitution's philosophy
  explicitly avoids elsewhere).

## R6. Materially-similar-plan detection: stdlib difflib, no new dependency

- **Decision**: normalize each plan's step descriptions (lowercase,
  whitespace-collapsed) into a sorted list (order-insensitive per the
  spec), then compare with `difflib.SequenceMatcher.ratio()` across the
  joined text. Same step count **and** ratio above a fixed threshold
  (proposed 0.85) ⇒ "materially similar" ⇒ one internal re-prompt.
- **Rationale**: this is a rare fallback path (a reasoned regeneration is
  expected to differ already, per the 2026-07-13 clarification) — a
  lightweight stdlib heuristic is proportionate; no ML/embedding-based
  similarity needed for v1.
- **Alternatives**: embedding-based semantic similarity (rejected —
  real cost/latency for a safety-net path that's expected to rarely fire);
  exact string equality only (rejected — too narrow, would miss trivial
  rewordings that are "the same plan" in substance).

## R7. Intent envelope tightened from `list[dict]` to a discriminated union

- **Decision**: `ChatTurn.intents` becomes
  `list[CreateSkillIntent | CreatePlanIntent | RevisePlanIntent | ReviseGoalIntent]`
  with a `type` discriminator, replacing 001's placeholder `list[dict]`.
- **Rationale**: 001 deliberately left this loose since it always returned
  `[]`; 002 is the first feature that actually applies intents, so this is
  the natural point to add real Pydantic validation per intent shape
  (Constitution I).
- **Alternatives**: keep `list[dict]` and validate manually per-application
  (rejected — loses Pydantic's declarative validation/error-feedback
  machinery that Constitution I's retry loop depends on).

## R8. Model tier: staying on Flash-Lite, flagged deviation

- **Decision**: continue using `gemini-3.1-flash-lite` (env `LLM_MODEL`,
  unchanged from 001) for wizard and plan-generation calls, rather than
  switching to a standard-tier Flash model as Constitution V's "generation
  uses the standard tier" language suggests.
- **Rationale**: live quota check (2026-07-13) found `gemini-3.5-flash` at
  only 20 RPD vs. `gemini-3.1-flash-lite` at 500 RPD. A single wizard
  intake (several turns) plus up to 3 regenerations could approach 20
  calls; 20 RPD would starve development within one or two test sessions.
  This is a pragmatic, explicitly flagged, config-only deviation (switching
  is a one-line env change per Constitution VI) — revisit when the paid
  tier lands at feature 005.
- **Alternatives**: switch to standard tier now and accept the quota pain
  (rejected — would materially slow this feature's own development and
  testing); split tiers (lite for wizard chit-chat, standard for the final
  plan-generation call only) — deferred as a future optimization, not
  necessary for correctness, and doubles the model-tier surface for
  marginal benefit at this stage.

## R9. Duplicate-name matching heuristic

- **Decision**: case-insensitive exact match plus a light fuzzy check
  (e.g., Levenshtein distance ≤ 2, or a simple substring/whitespace-
  normalized comparison) against the user's existing skill names, computed
  client-side over the already-fetched skill list.
- **Rationale**: cheap, no dependency needed (a small pure-JS distance
  function is sufficient at this list size — a handful of skills per
  user), good enough to catch "Swimming" vs "swimming" vs "Swiming"
  without over-engineering a real fuzzy-matching library.
- **Alternatives**: server-side fuzzy search (rejected — unnecessary round
  trip for a small, already-fetched list).
