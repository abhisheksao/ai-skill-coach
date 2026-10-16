# Feature Specification: Wizard & Plan Generation

**Feature Branch**: `002-wizard-and-plan`

**Created**: 2026-07-11

**Status**: Clarified — ready for `/speckit-plan`

**Input**: User description: "A user picks a skill to learn; a wizard conversation elicits current level, target, timeline, weekly time; the system generates a structured learning plan the user can review."

## Clarifications

### Session 2026-07-13

- Q: Duplicate skill (user adds "swimming" twice)? → A: warn, then let them
  proceed. The wizard notices an existing skill with the same/similar name and
  asks whether to continue as a new pursuit or open the existing one; the
  user decides. No hard block.
- Q: Is "reject and regenerate" in scope for the plan review screen? → A:
  yes. The review screen offers a regenerate action alongside accept, capped
  at **3 regenerations** per intake; on the 4th rejection the screen stops
  offering regenerate and instead routes the user back into the wizard to
  revise the underlying goal/timeline/level/weekly-time facts (a fresh
  intake resets the cap).
- Q: What if a regenerated plan comes back essentially unchanged from the one
  just rejected? → A (revised 2026-07-13): detect it and force the LLM to
  think harder. Before showing the new plan to the user, the system compares
  it to the immediately prior rejected plan; if materially similar (same
  step count and step descriptions match closely, order-insensitive), it
  automatically re-prompts the LLM once, explicitly instructing it to
  produce a meaningfully different approach — this internal retry is
  transparent to the user and does **not** consume one of their 3 visible
  regeneration attempts. If the retried plan is still similar, it is shown
  anyway (bounded to one internal retry — no open-ended loop).
- Q: Plan size and wizard-turn bounds? → A: plans contain **3–12 steps**;
  the wizard force-summarizes the intake after **12 conversational turns**
  even if a topic is still unresolved (asks the user to confirm what it has
  and proceeds).
- Q: Should regenerate capture *why* the user rejected the plan, so the LLM
  can target the actual complaint instead of just retrying? → A: yes. Tapping
  regenerate requires picking one of three reasons — **too much**, **too
  easy**, **not quite right** — plus an optional one-line note; the reason
  and note are passed as context to the regeneration call so the LLM adjusts
  difficulty/pace/focus accordingly, rather than guessing. This also weakens
  the materially-similar case above: a plan regenerated because it was "too
  easy" is expected to differ, so the similarity nudge becomes a fallback
  safety net rather than the primary mechanism.

### Session 2026-07-12

- Q: How does one LLM turn produce both a coaching reply and typed intents? →
  A: a single structured call returning `{reply, intents[]}` (option A — keep it
  simple; decision 2026-07-12). Any later change to this pattern is localized to
  the LLM-integration layer. Validation failure/retry/degradation per
  Constitution I applies to the whole response.
- Q: Is there a separate `create_goal` intent? → A: no — wizard completion emits
  `create_skill` + `create_plan`, and `create_plan` creates the Goal, Plan, and
  Steps together in the atomic completion write.
- Q: Can two plans serve the same goal? → A: yes (approved 2026-07-12): every plan
  links to the goal it serves, and plan revisions create successor plans keeping
  history — with exactly one active (non-superseded) plan per skill. Example:
  goal unchanged, training days change → regenerated plan points at the same goal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Onboard a skill through the wizard (Priority: P1)

A signed-in user chooses to learn a new skill (e.g., swimming). A guided coaching
conversation asks, one at a time: their current level, what they want to achieve,
by when, and how much time per week they can invest. The conversation feels like a
coach intake, not a form — but it always covers exactly these four topics.

**Why this priority**: This intake is the product's core differentiator; every plan,
check-in, and reminder derives from what the wizard captures.

**Independent Test**: Start a new skill, answer the four wizard questions in plain
language, and confirm the captured answers (level, target, timeline, weekly budget)
are played back accurately for confirmation — even before any plan exists.

**Acceptance Scenarios**:

1. **Given** a user with no skills, **When** they create a skill and enter the
   wizard, **Then** the conversation elicits current level, target achievement,
   timeline, and weekly time budget, in a coach-like tone, one topic at a time.
2. **Given** a user mid-wizard, **When** they give a vague answer ("some experience"),
   **Then** the wizard asks one focused follow-up rather than moving on with an
   unusable value.
3. **Given** all four topics answered, **When** the wizard completes, **Then** it
   summarizes the captured intake and asks the user to confirm before generating a
   plan.
4. **Given** a user who abandons the wizard midway, **When** they return, **Then**
   the partial intake is gone by design (transient, client-only) and a fresh
   intake starts; no partial skill, goal, or plan exists anywhere in coaching
   state.

---

### User Story 2 - Receive and review a structured plan (Priority: P1)

After the intake is confirmed, the system generates a structured learning plan — an
ordered sequence of steps, each with a practice cadence — and shows it on a review
screen the user can read before accepting.

**Why this priority**: The plan is the artifact the rest of the product operates on;
without it there are no check-ins, progress, or reminders.

**Independent Test**: Complete an intake and verify a plan appears with ordered
steps and cadences consistent with the stated timeline and weekly budget, and that
the same plan is faithfully recorded in the coaching state.

**Acceptance Scenarios**:

1. **Given** a confirmed intake, **When** plan generation completes, **Then** the
   user sees a goal statement plus an ordered list of steps, each with a cadence
   (e.g., "3× per week"), and the total weekly load does not exceed the user's
   stated weekly time budget.
2. **Given** a generated plan, **When** the coaching state is inspected, **Then**
   goal, plan, and steps exist exactly as displayed, attached to the right skill and
   user, with step order preserved.
3. **Given** plan generation output that fails validation, **When** retries (max 2)
   also fail, **Then** the user receives a graceful conversational reply and no
   partial plan is written to the coaching state (Constitution I).
4. **Given** a displayed plan the user finds too demanding, **When** they
   choose regenerate and select **too much** (with or without a note), **Then**
   a new, less intense plan is generated for the same confirmed intake and
   replaces the displayed one; this can happen up to 3 times.
5. **Given** a displayed plan the user finds unchallenging, **When** they
   select **too easy** and regenerate, **Then** the new plan is noticeably
   more demanding within the stated weekly time budget.
6. **Given** a user who has already regenerated 3 times, **When** they reject
   the plan again, **Then** the review screen no longer offers regenerate and
   instead invites them back into the wizard to revise their goal, timeline,
   level, or weekly time.
7. **Given** a regenerated plan that is materially similar to the one just
   rejected, **When** the system detects this before display, **Then** it
   silently re-prompts the LLM once for a meaningfully different approach and
   shows the result — the user's visible attempt count does not increase.

---

### User Story 3 - Manage multiple skills (Priority: P2)

A user can see the skills they are pursuing as cards, add a new skill, and switch
between skills; each skill's wizard state and plan are independent.

**Why this priority**: Multi-skill support shapes navigation and data scoping and is
cheap now, expensive to retrofit.

**Independent Test**: Complete the wizard for one skill; start but abandon a
second. Verify only the completed skill exists as a card, and completing the
second skill's wizard later adds it independently.

**Acceptance Scenarios**:

1. **Given** a user with one onboarded skill, **When** they complete the wizard
   for a second, **Then** both appear as cards and selecting one opens that
   skill's own conversation and plan. Skills exist only once their wizard
   completes — an abandoned wizard leaves no card and no record.
2. **Given** two skills, **When** a conversation happens within skill A, **Then**
   nothing about skill B's goal, plan, or wizard state changes.

---

### Edge Cases

- User asks an off-topic question mid-wizard → the coach answers briefly or defers,
  then steers back to the pending intake topic; intake state is not lost.
- Contradictory answers (e.g., "compete in 3 months" + "30 minutes per week") → the
  wizard flags the tension and asks the user to adjust one side; it does not silently
  generate an implausible plan.
- User states a timeline in an unusual form ("by my birthday") → wizard converts to a
  concrete date with the user's confirmation.
- Duplicate skill (user adds "swimming" twice) → the wizard warns ("you're
  already learning swimming — start a new pursuit, or open the existing
  one?") and lets the user decide; no hard block (resolved 2026-07-13).
- The AI proposes a plan whose structure is valid but content is unsafe or
  nonsensical for the stated level → user can reject at review and regenerate,
  up to 3 times per intake; the 4th rejection routes back into the wizard to
  revise the underlying facts rather than offering a 4th regeneration
  (resolved 2026-07-13 — see Requirements FR-011).
- A regenerated plan comes back materially similar to the one just rejected
  → detected automatically and the system re-prompts the LLM once for a
  meaningfully different approach before showing anything to the user; this
  internal retry does not consume a visible regeneration attempt (revised
  2026-07-13 — see FR-011).
- Wizard conversation runs long without completing all four topics → force-
  summarized at 12 turns; the coach confirms what it has and proceeds
  (resolved 2026-07-13 — see FR-010).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to create a skill by explicit selection/entry and
  see all their skills; conversations are always scoped to an explicitly selected
  skill (no free-form skill routing in v1).
- **FR-002**: The wizard MUST elicit exactly four intake facts — current
  knowledge/skill level, target achievement, timeline (target date), and weekly
  time budget (captured as training days per week and hours per day) — and MUST
  NOT be extended with additional question topics in v1 (fixed question set;
  depth/follow-ups within a topic are allowed).
- **FR-003**: The wizard MUST play back the captured intake for user confirmation
  before plan generation.
- **FR-004**: Intake data is transient on the client — it passes from one wizard
  screen/turn to the next and is never persisted server-side. Nothing is written
  to coaching state until the user confirms the complete intake, at which point
  skill, goal, and plan are created together (one atomic completion). Abandoning
  the wizard discards the transient data; returning starts a fresh intake
  (decision 2026-07-12).
- **FR-005**: Plan generation MUST produce a goal plus an ordered set of steps, each
  with a cadence, respecting the user's stated weekly time budget and timeline.
- **FR-006**: All state changes from conversation (skill creation, plan creation,
  goal creation) MUST flow through the typed-intent pipeline with schema validation,
  retry-with-error-feedback (max 2), and graceful text-only degradation
  (Constitution I). Malformed AI output MUST be recorded for telemetry.
- **FR-007**: The plan shown to the user and the plan recorded in coaching state
  MUST be identical (single source of truth; the review screen renders the recorded
  plan, not the raw AI output).
- **FR-008**: The system MUST assemble conversation context from the user's profile
  plus the active skill's coaching state (goal, plan, steps) so the coach never asks
  for facts it already has.
- **FR-009**: The intent→state translation layer and the context assembly MUST have
  unit tests covering every intent in the v1 vocabulary that this feature uses
  (`create_skill`, `create_plan`, `revise_plan`, `revise_goal`) plus validation
  failure and retry paths (Constitution VIII).
- **FR-010**: Plan size MUST be bounded to 3–12 steps. The wizard MUST force-
  summarize the intake after 12 conversational turns even if a topic remains
  unresolved, confirming with the user what was captured before proceeding.
- **FR-011**: The plan review screen MUST offer a regenerate action in
  addition to accept. Selecting regenerate MUST require the user to pick one
  reason — **too much**, **too easy**, or **not quite right** — and MAY
  accept an optional one-line note; both are passed as context to the
  regeneration call so the LLM targets the actual complaint (adjusting
  difficulty, pace, or focus) rather than producing an arbitrary variation.
  Regeneration is capped at 3 user-visible attempts per intake; on a 4th
  rejection the screen MUST stop offering regenerate and instead route the
  user back into the wizard to revise the intake facts (a new intake resets
  the cap). Before a regenerated plan is shown to the user, the system MUST
  compare it to the immediately prior rejected plan; if materially similar
  (same step count and closely matching step descriptions, order-insensitive)
  — which is expected to be rare when a reason was given — the system MUST
  automatically re-prompt the LLM once with an explicit instruction to
  produce a meaningfully different approach, transparently to the user and
  without consuming a visible attempt. This internal retry is bounded to one
  extra call per regeneration — if the result is still similar, it is shown
  as-is.
- **FR-012**: When a user starts a skill whose name matches an existing
  skill, the system MUST warn and let the user choose to proceed as a new
  pursuit or open the existing skill; it MUST NOT block the action.

### Key Entities

- **Skill**: A pursuit the user has chosen (name, created date); owns its goal,
  plan, and sessions. Belongs to exactly one user.
- **Goal**: The target achievement + timeline captured at intake. Immutable;
  revisions create successor goals (Constitution III).
- **Plan**: The generated learning program for a skill; owns ordered steps and
  links to the goal it serves. Revisions create successor plans (history
  preserved); exactly one active plan per skill.
- **Step**: One unit of the plan — description, order, cadence (how often it should
  be practiced). Status is never stored; it is derived from check-ins
  (Constitution II).
- **Intake (wizard state)**: The four captured facts and the wizard's position;
  transient client-side state only, passed screen to screen, never persisted
  server-side. On confirmation it feeds the atomic skill/goal/plan creation, then
  is discarded.
- **Regeneration reason**: A transient selection (too much / too easy / not
  quite right) plus an optional note, captured when the user taps regenerate.
  Passed as context to that one regeneration call; not persisted and not
  part of the recorded Plan.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fresh user can go from "learn swimming" to a visible, correctly
  recorded plan in a single conversation.
- **SC-002**: 100% of schema-invalid AI outputs during testing recover without a
  user-visible failure (retry succeeds or graceful degradation engages), and each
  occurrence is captured in telemetry.
- **SC-003**: Plans respect stated constraints: in acceptance testing across varied
  intakes, no generated plan exceeds the user's weekly time budget or ignores the
  stated timeline.
- **SC-004**: Coaching-state audit for a completed onboarding shows exactly one
  goal, one plan, and its ordered steps for the skill — no orphans, duplicates, or
  partial writes from failed generations.
- **SC-005**: Unit tests cover every intent used by this feature, including
  failure/retry paths; suite runs in CI.
- **SC-006**: In acceptance testing, regenerating with "too much" produces a
  measurably less demanding plan (fewer steps and/or lower cadence) and
  "too easy" produces a measurably more demanding one, for the same intake.

## Assumptions

- Text chat only; voice arrives in feature 003 and must require no changes to this
  feature's conversation logic (Constitution IV).
- The wizard's coach-like phrasing may vary freely between runs; only the four-topic
  coverage, confirmation step, and captured facts are contract.
- Cadence is expressed as times-per-week in v1; calendar-day scheduling (e.g.,
  "Mondays and Thursdays") is deferred.
- One active plan per skill in v1; `revise_plan` creates a superseding plan linked
  to the goal it serves (schema approved 2026-07-12), but a full plan-revision UX
  is deferred to later features.
- Wizard and plan-generation conversations happen in the user's preferred language
  across the launch set (EN, HI, ES, FR, DE — Constitution X); plan content
  (goal, steps) is generated in that language. Intent JSON and schema field names
  remain language-neutral.
