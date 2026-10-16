# Tasks: Wizard & Plan Generation

**Input**: Design documents from `/specs/002-wizard-and-plan/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api.md

**Tests**: included — FR-009 explicitly requires unit tests for the
intent→Cypher translator and context builder; contracts/api.md lists 7
contract tests. Write tests with or before the code they cover.

**Organization**: grouped by user story from spec.md. US1 = wizard intake,
US2 = plan review + regeneration, US3 = multi-skill management. No Setup
phase — 002 reuses 001's running scaffolds; work starts at Foundational.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- Paths are repo-relative; structure per plan.md

---

## Phase 1: Foundational (blocks all user stories)

- [x] T001 [P] `api/src/skillcoach_api/models/intents.py`: `StepPayload`,
      `CreateSkillIntent`, `CreatePlanIntent` (nests goal fields + `steps:
      list[StepPayload]`, `min_length=3, max_length=12`), `RevisePlanIntent`,
      `ReviseGoalIntent`; discriminated `Intent` union on `type` (data-model.md)
- [x] T002 `api/src/skillcoach_api/models/chat.py`: EXTEND —
      `ChatTurn.intents: list[Intent]` (replaces 001's `list[dict]`
      placeholder, research R7); `ChatRequest` gains `skill_id: UUID | None`,
      `new_skill_name: str | None`; `ChatResponse` gains `skill_id`
- [x] T003 [P] `api/src/skillcoach_api/models/skills.py`: `SkillSummary`
      (list card shape), `SkillDetail` (goal + plan + steps + derived
      `generation`)
- [x] T004 `api/src/skillcoach_api/services/skills.py`: `SkillsService` —
      `list_skills(user_id)`, `get_skill(user_id, skill_id)`,
      `regeneration_count(skill_id)` (derived via `SUPERSEDES` chain depth,
      research R5); all Cypher parameterized and scoped to `user_id`
- [x] T005 [P] `api/src/skillcoach_api/services/plan_similarity.py`:
      `is_materially_similar(old_steps, new_steps) -> bool` — stdlib
      `difflib.SequenceMatcher`, order-insensitive, normalized text
      (research R6); tests `api/tests/test_plan_similarity.py`
- [x] T006 `api/src/skillcoach_api/services/intent_apply.py`:
      `apply_intents(intents, user_id) -> ApplyResult` — **one Neo4j
      transaction per call** (atomicity, FR-004); one Cypher builder per
      intent type (`create_skill`, `create_plan` bundles Goal+Plan+Steps,
      `revise_plan` supersedes the active Plan, `revise_goal` supersedes
      the active Goal); tests `api/tests/test_intent_apply.py` — one test
      per intent, an atomicity test (simulated mid-transaction failure
      leaves no nodes), tenant-scoping test (FR-009)
- [x] T007 `api/src/skillcoach_api/services/context_builder.py`:
      `build_context(user_id, skill_id, session_id) -> Context` — profile
      always; if `skill_id` set, that skill's goal/plan/steps via
      `SkillsService`; last ~20 messages for `session_id`; user-turn count
      for the 12-turn cap (FR-010, research R1); tests
      `api/tests/test_context_builder.py`
- [x] T008 `api/src/skillcoach_api/services/llm.py`: EXTEND — wizard-turn
      system prompt (four-topic intake, confirm-before-plan per FR-003,
      12-turn force-summarize instruction) and a regenerate-turn system
      prompt (reason/note/current-plan context; a "produce a meaningfully
      different approach" variant for the internal similarity retry,
      research R6); both reuse the existing structured-call shape (option A)

**Checkpoint**: foundation ready — user stories can begin

---

## Phase 2: User Story 1 — Onboard a skill through the wizard (P1) 🎯 MVP

**Goal**: guided four-topic intake; confirming it atomically writes
Skill+Goal+Plan+Steps.

**Independent Test**: spec US1 scenarios 1–4 + quickstart scenarios 1, 2, 4.

- [x] T009 [US1] `api/src/skillcoach_api/routes/chat.py`: EXTEND — done as
      part of Phase 1 (wiring the new foundational services required
      exercising them through the real route to be testable); threads
      `skill_id`/`new_skill_name` into `context_builder`, calls the wizard
      or coaching prompt, applies whichever intents the turn produced,
      returns the resolved `skill_id`. Covered so far by
      `test_chat_contract.py`'s wizard-completion test (FakeIntentApply).
- [x] T010 [US1] `api/tests/test_chat_wizard.py` covers the 12-turn
      force-summarize boundary specifically, and atomicity *through the
      route* using the real `IntentApplyService` + a fake Neo4j driver
      (not just `FakeIntentApply`) — extends 001's `test_chat_contract.py`
      patterns with route-level, not just service-level, atomicity proof.
      Was already implemented in 413d454 (Phase 2) but left unchecked;
      confirmed all 4 tests pass on re-run.
- [x] T011 [US1] `app/src/lib/api.ts`: EXTEND `postChat` to send/receive
      `skill_id`, send `new_skill_name`; added `getSkills`/`getSkill` too
      (needed by T012/T013 below — see T014 note)
- [x] T012 [US1] `app/src/app/(main)/skills.tsx`: "Add skill" entry — name
      text field; client-side duplicate check (Levenshtein ≤2,
      case-insensitive, research R9) against `GET /v1/skills` before
      entering the wizard (FR-012) — native Alert with continue-existing /
      start-new / cancel, never a hard block. Also the home dashboard list
      of skill cards (pulled forward from Phase 4/T019 — needed as the
      landing screen once skills exist; full card polish stays Phase 4)
- [x] T013 [US1] `app/src/app/(main)/wizard.tsx`: shares a new
      `useChatSession` hook + `ConversationView` component with `chat.tsx`
      (extracted rather than duplicated — both screens need identical
      send/optimistic-update/bubble-list behavior), parameterized by
      `skill_id` (null while onboarding); on a response whose `skill_id`
      becomes non-null, navigates to `plan-review.tsx`. `chat.tsx` itself
      was also fixed to scope message history by `skill_id`
      (`.eq`/`.is('skill_id', null)`) — 001's query had no such filter,
      which would have silently mixed conversations across skills.
      Auth-gate landing (`_layout.tsx`, `index.tsx`) now routes to
      `/skills` instead of directly to `/chat`.

**Checkpoint**: US1 passes — full wizard conversation completes; Neo4j
shows Skill+Goal+Plan+Steps written atomically

---

## Phase 3: User Story 2 — Receive and review a structured plan (P1)

**Goal**: review screen renders the persisted plan; regenerate is capped at
3 attempts with a reason required and a similarity-guarded internal retry.

**Independent Test**: spec US2 scenarios 1–7 + quickstart scenarios 3, 5, 6, 7.

- [x] T014 [P] [US2] `api/src/skillcoach_api/routes/skills.py`:
      `GET /v1/skills`, `GET /v1/skills/{skill_id}` (404 on not-found /
      not-owned, indistinguishable per tenant scoping) — done early, in
      Phase 2, since the wizard-completion flow (T012 duplicate check,
      T013→plan-review navigation) needed both endpoints to be usable at
      all. Only `POST .../plan/regenerate` (T015) remains for this task.
- [x] T015 [US2] `api/src/skillcoach_api/routes/skills.py`:
      `POST /v1/skills/{skill_id}/plan/regenerate` — reads the skill via
      `SkillsService` (context built inline: profile language + skill
      detail; the generic `context_builder` wasn't a fit since it needs a
      `session_id` regenerate doesn't have); `generation >= 3` → 409
      `regeneration_cap_reached` before `budget.acquire` or any LLM call;
      else calls `llm.generate_regeneration`, runs `plan_similarity`
      against the current plan, re-prompts once (uncounted,
      `force_different=True`) if materially similar, then
      `apply_intents([revise_plan])` and re-reads the skill for the
      response
- [x] T016 [US2] Contract tests `api/tests/test_skills_contract.py`:
      list/detail scoping (from Phase 2) + regenerate happy path, 409 at
      the cap (zero LLM calls asserted), similarity-triggered internal
      retry (exactly one extra LLM call, exactly one `apply_intents` call
      — the near-duplicate result is discarded, generation moves by
      exactly 1 not 2), reason/note reaching the LLM, 404, auth-required.
      10/10 passing; 78/78 across the whole api suite.
- [x] T017 [US2] `app/src/app/(main)/plan-review.tsx`: Regenerate added —
      reason chips (too much / too easy / not quite right, required) +
      optional note, `POST .../regenerate`, updates the displayed plan in
      place on success. Client-side hides the option once
      `generation >= 3` (server still enforces regardless — defense in
      depth, not the source of truth).
- [x] T018 [US2] Cap-reached UX: routes to `/chat?skillId=X&promptRevise=1`
      — **not** `wizard.tsx` as originally sketched (that screen is for
      `skill_id === null` only; an existing skill's cap-reached case is
      exactly what `chat.tsx` already handles). `chat.tsx` reads
      `promptRevise` and appends a local, non-persisted nudge bubble
      (`plan.regenerate.capReachedTitle`) — no LLM call spent just to
      open the topic; the user's actual next message flows through the
      ordinary pipeline and may produce `revise_goal`/`revise_plan`.

**Checkpoint**: US2 passes — plan generation, both regenerate directions,
and the 3-attempt cap all verified end to end

---

## Phase 4: User Story 3 — Manage multiple skills (P2)

**Goal**: skills render as independent cards; conversation in one never
touches another.

**Independent Test**: spec US3 scenarios 1–2 + quickstart scenarios 8, 9.

- [x] T019 [US3] `app/src/app/(main)/skills.tsx`: already complete from
      Phase 2's pull-forward — every skill from `GET /v1/skills` renders as
      a card, tapping one routes straight to `/chat?skillId=X`, never
      touching `/wizard`. Verified again here (tsc/lint/jest/export all
      clean).
- [x] T020 [US3] **Found and fixed a real isolation bug while writing this
      test**: `revise_plan`/`revise_goal` matched a skill by **name**, not
      id. FR-012 explicitly allows two skills to share a name (the
      duplicate warning is dismissible), so once that happens, a
      name-based `MATCH` is ambiguous — a genuine cross-skill leak, not a
      hypothetical one. Fixed in `intent_apply.py`: every mutating
      operation now matches by id, supplied by the caller's already-
      resolved `skill_id` (`chat.py`'s `body.skill_id`, or regenerate's
      path param) — never re-derived from a name the LLM might echo back.
      `create_plan` uses the id generated for its paired `create_skill` in
      the same atomic batch. Removed the now-vestigial `skill_name` field
      from `RevisePlanIntent`/`ReviseGoalIntent` entirely (kept on
      `CreatePlanIntent`, where it's still naturally present and harmless).
      New `tests/test_skill_isolation.py` (3 tests) exercises the exact
      duplicate-name scenario end to end through the real route +
      `IntentApplyService` + `ContextBuilder`, proving skill A and skill B
      — same name, different id — never cross-contaminate. 82/82 across
      the full api suite.

**Checkpoint**: all three user stories independently functional

---

## Phase 5: Polish & Cross-Cutting

- [x] T021 [P] `api/README.md`: document the 3 new endpoints and the
      regenerate cap/409 behavior
- [x] T022 Run all 10 `quickstart.md` scenarios (EN+HI full, ES/FR/DE
      smoke) — feature exit gate (Constitution VIII). All 10 scenarios
      pass live on-device (EN, see quickstart.md's Results section for
      detail); surfaced 4 real UX gaps plus a target-date bug and a
      stale-copy issue on the regenerate CTA, all fixed and covered by
      new/extended tests: Android `KeyboardAvoidingView` no-op on both
      the wizard/chat screens AND (separately — first fix wasn't
      enough) the home screen's add-skill field, `app.json`
      `softwareKeyboardLayoutMode: "resize"` — **needs a native rebuild,
      `npx expo run:android`, to take effect**), too much free-typing
      for closed-set wizard questions (added `suggested_replies`
      tappable chips, additive only), stale add-skill field state on
      `skills.tsx` after returning from the wizard, no way back to a
      skill's plan/goal after the initial review (`plan-review.tsx` now
      doubles as the permanent skill-detail screen), and "Not quite
      right?" reading oddly once that screen is revisited long after
      plan creation (retitled to "Want to adjust this plan?" across all
      5 locales). Language sampling completed 2026-07-15: HI full pass
      done live by the product owner; ES/FR/DE smoke done live via
      direct API calls (UI strings already localized, one live reply
      per language confirmed fully in-language) — see quickstart.md's
      updated Results section for the actual replies.
- [x] T023 `specs/README.md`: update 002's status to reflect implementation
      complete now that T022 passes

  **⏸ RESUME WHEN AN iOS DEVICE IS AVAILABLE** (tracked in
  `specs/README.md`'s "Deferred: iOS device validation" section): the
  wizard's `suggested_replies` chips, keyboard-avoidance behavior, and the
  regenerate flow have only been eyeballed on Android + Chrome web
  (Playwright's `wizard-plan.spec.ts`) — no iOS-specific rendering pass yet.

---

## Dependencies & Execution Order

- **Phase 1 → Phase 2/3/4**: T001 blocks T002/T006; T004 blocks T009/T015;
  T005 blocks T015; T007 blocks T009 (context assembly needed before the
  route can use it); T008 blocks T009/T015 (prompts must exist first)
- **US1 before US2**: US2's review screen has nothing to review until a
  wizard has completed at least once — build/verify T009–T013 before T014+
- **US3 depends on US1/US2 existing** (needs completed skills to manage) but
  is otherwise independent of US2's regenerate mechanics — T019/T020 can
  start once T012/T013 land
- **T018 depends on T015** (the 409 response) and **T013** (wizard
  navigation already built)
- **T022 last** — exit gate, run only once T009–T020 are all in place

## Implementation Strategy

Foundational (T001–T008) is one batch — none of it is independently
demoable, so implement it together, then verify with `test_intent_apply.py`
and `test_context_builder.py` passing before moving on. MVP slice = Phase 1
+ Phase 2 (a user can complete a wizard and see a plan get written). Phase 3
adds the regenerate loop; Phase 4 adds multi-skill management. Commit after
each phase, matching the "implement → verify → commit → push" rhythm used
throughout feature 001.
