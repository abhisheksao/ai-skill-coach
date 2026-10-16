# Feature Specification: Progress Loop & Notifications

**Feature Branch**: `004-progress-and-notifications`

**Created**: 2026-07-11

**Status**: Draft — run clarification before planning (mandatory for this feature)

**Input**: User description: "The coach checks on progress, celebrates it, helps diagnose obstacles, adapts goals, and proactively reminds users who fall behind their planned cadence; tapping a reminder resumes coaching with full awareness of the gap."

## Clarifications

### Session 2026-07-13

- Q: Is there a way to see and manage existing goals/plans without opening a
  chat, and how do users mark progress if not conversationally? → A: yes —
  added as User Story 6 (home dashboard) and User Story 7 (direct step
  completion). A step can be marked done via a UI tap in addition to
  conversation; the tap constructs the same `complete_step` (full) or
  `log_checkin` (partial) intent directly, skipping the LLM entirely, and
  is validated and applied through the identical pipeline as an
  LLM-produced intent (Constitution I, amended). `CheckIn` gains a `source`
  property (`conversation` | `ui_tap`) to record which path produced it.
- Q: Can a goal or plan be deleted or ended from the UI (e.g., because it
  looks stale)? → A: no. Per Constitution III, no UI path may delete or
  terminally end a goal — it stays open indefinitely as a standing pursuit.
  A stale-looking goal is surfaced with three options: continue as-is,
  revise the timeline/goal in conversation (`revise_goal`, already in
  scope), or start a new pursuit alongside it. There is no delete action.

### Session 2026-07-17

- Q: What triggers the "behind cadence" nudge (FR-008)? → A: no check-in
  within 1.5x the expected interval for any active step.
- Q: What frequency cap and quiet hours should apply to nudges (FR-010)?
  → A: max 1/skill/day, max 3/week, sent in the user's local daytime.
- Q: How should "streak" be defined (FR-005), distinct from cadence
  adherence? → A: consecutive calendar days with a check-in for that skill.
- Q: FR-014 references a "configured threshold" for marking a goal stale on
  the dashboard, but no value was defined. What should it be? → A: 14 days
  with no check-in activity.
- Q: How long of inactivity counts as an abandoned session ending (FR-006)?
  → A: 30 minutes.
- Q: How many past session summaries should a new session's context include
  (FR-007)? → A: 5 (the spec's original proposal), confirmed as a default.
- Q: Should the thresholds resolved above be hardcoded or configurable? → A:
  defined as named constants in one central module (FR-018 added), not
  environment variables — these are rare-to-change tuning values, not
  secrets/per-deploy config, so a code-level constant is sufficient; all
  defaults above (1.5x, 1/skill/day + 3/week, 14 days, 30 minutes, N=5) are
  starting values, not scattered inline literals.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Check in on practice (Priority: P1)

After practicing, the user tells the coach how it went ("did my drills, breathing
felt better but flip turns are rough"). The coach records the check-in against the
right plan step — capturing outcome and how the user felt — celebrates wins, and when
the user is done marks steps complete.

**Why this priority**: Check-ins are the raw material for everything else in this
feature — progress display, memory, and cadence detection all derive from them.

**Independent Test**: In a session, report a practice; verify a check-in is recorded
against the correct step with outcome and sentiment, and that the derived progress
view reflects it — with no notifications or summaries needed.

**Acceptance Scenarios**:

1. **Given** a user with an active plan, **When** they report a practice in
   conversation (voice or chat), **Then** a check-in is recorded against the correct
   step with timestamp, outcome, and sentiment, and the coach acknowledges
   specifically (references the step, celebrates progress).
2. **Given** a user reporting difficulty ("I keep sinking when I try to float"),
   **When** the coach responds, **Then** the obstacle is recorded against the step
   and the coach offers a concrete workaround or adjustment.
3. **Given** a user who has finished a step's work, **When** they say so, **Then**
   the step is marked complete and the coach orients them to the next step.
4. **Given** an ambiguous report (which step? which day?), **When** the coach can't
   confidently attribute it, **Then** it asks one clarifying question rather than
   guessing.

---

### User Story 2 - See progress at a glance (Priority: P2)

Each skill has a progress view: completed steps, current streaks, and how well the
user is keeping to their planned cadence — all computed from recorded check-ins.

**Why this priority**: Visible momentum is a core retention mechanic; it also makes
the check-in loop feel worthwhile.

**Independent Test**: Record a known sequence of check-ins, open the progress view,
and verify streaks, completed steps, and cadence adherence match hand-computed
values.

**Acceptance Scenarios**:

1. **Given** a user with recorded check-ins, **When** they open a skill's progress
   view, **Then** they see completed steps, current streak, and cadence adherence,
   all consistent with their check-in history.
2. **Given** the same underlying check-ins, **When** progress is viewed from any
   platform or recomputed at any time, **Then** the numbers are identical — there is
   no stored counter to drift (Constitution II).

---

### User Story 3 - The coach remembers (Priority: P2)

When a session ends, the system produces a short summary of what happened. Future
sessions open with the coach aware of recent history ("Last time flip turns were
frustrating you — how did this week go?") without the user recapping.

**Why this priority**: Continuity is what separates a coach from a chatbot; it also
keeps conversation context small and cheap.

**Independent Test**: Hold a session with distinctive content, end it, start a new
session, and verify the coach's opening reflects the prior session's summary.

**Acceptance Scenarios**:

1. **Given** a session ends, **When** summarization runs, **Then** a concise summary
   is stored against that session covering topics, check-ins, obstacles, and
   commitments made.
2. **Given** a new session starts, **When** the coach composes its first message,
   **Then** it demonstrably has the last several session summaries available and
   references relevant recent history naturally.
3. **Given** summarization fails, **When** the next session starts, **Then**
   coaching still works (older summaries or graceful absence); failure is logged.

---

### User Story 4 - Nudge when behind cadence (Priority: P1)

A user who falls behind their planned cadence receives a push notification. Tapping
it deep-links into that skill's coaching session, where the coach already knows about
the gap and opens with it — supportively, not punitively.

**Why this priority**: Proactive outreach is the promise of the product ("the app
checks on you"); paired with check-ins it closes the behavior loop.

**Independent Test**: Set up a plan with a known cadence, record no check-ins past
the threshold, verify exactly one reminder arrives, and confirm tapping it opens the
right skill with a gap-aware opening message.

**Acceptance Scenarios**:

1. **Given** a user behind their planned cadence, **When** the daily cadence scan
   runs, **Then** they receive a push notification referencing the skill (and the
   coach's tone in copy is encouraging).
2. **Given** the user taps the notification, **When** the app opens, **Then** it
   lands directly on that skill's session and the coach's opening message
   acknowledges the specific gap (e.g., which step was missed, how long it's been).
3. **Given** a user on cadence, **When** the scan runs, **Then** they receive
   nothing.
4. **Given** notifications are denied at the OS level, **When** the scan finds them
   behind, **Then** no error occurs, and the in-app coach still raises the gap at
   the next session.

---

### User Story 5 - Adjust the goal (Priority: P3)

Life changes; the user tells the coach their target or timeline moved ("the
competition got pushed to spring"). The coach captures the revised goal while
preserving the original, and future coaching reflects the new target.

**Why this priority**: Goal drift is inevitable over multi-week plans, but the loop
functions without revision in the short term.

**Independent Test**: Revise a goal in conversation; verify a new goal supersedes
the old, the old remains in history, and the coach subsequently coaches to the new
goal.

**Acceptance Scenarios**:

1. **Given** an active goal, **When** the user revises it in conversation, **Then**
   a new goal is recorded superseding — not overwriting — the old one
   (Constitution III), and the coach confirms the change.
2. **Given** a revised goal, **When** a later session begins, **Then** the coach
   works toward the new goal and can reference the trajectory ("you originally
   aimed for October").

---

### User Story 6 - See all pursuits at a glance (Priority: P2)

Signing in lands the user on a home dashboard: every skill they're pursuing,
shown as a card with its goal and active plan, without needing to open a
conversation to check on any of them.

**Why this priority**: A home dashboard is the natural landing surface for a
returning user with several pursuits; it turns "did I do anything this week?"
into a glance instead of a chat.

**Independent Test**: With two or more skills in different states (one on
cadence, one stale), open the app and verify both render as cards with
accurate goal/plan/progress information, matching what each skill's
progress view (User Story 2) shows.

**Acceptance Scenarios**:

1. **Given** a user with at least one goal and its linked plan, **When**
   they sign in, **Then** the home dashboard shows a card per skill (goal as
   the parent, plan as the child) reflecting current progress.
2. **Given** a user with zero skills, **When** they sign in, **Then** the
   dashboard shows an empty state guiding them to start one (feature 002).
3. **Given** a goal with no recent activity, **When** its card renders,
   **Then** it is visibly marked stale and offers continue / revise-in-
   conversation / start-new — never a delete action (Constitution III).
4. **Given** the same underlying data, **When** the dashboard and a skill's
   dedicated progress view (User Story 2) are compared, **Then** the
   numbers agree — both are derived from the same CheckIn records
   (Constitution II).

---

### User Story 7 - Mark a step done without a conversation (Priority: P2)

From a card on the home dashboard, the user taps a step to mark it fully
complete or as partial progress — no conversation required.

**Why this priority**: Not every practice deserves a chat; a fast, direct
way to log "done" keeps the check-in habit low-friction for routine
updates, while conversation stays available for anything that needs
discussion (obstacles, adjustments).

**Independent Test**: Tap a step to mark it complete; verify a CheckIn
record is created with `source: ui_tap`, no LLM call is made, and the
dashboard/progress view update immediately.

**Acceptance Scenarios**:

1. **Given** a step on a plan card, **When** the user taps "mark complete,"
   **Then** a `complete_step` intent is constructed directly by the client,
   validated against the same schema as a conversational intent, and
   applied by the same deterministic translator (Constitution I) — with no
   LLM call in this path.
2. **Given** a step the user practiced but didn't finish, **When** they tap
   "log partial progress," **Then** a `log_checkin` intent is recorded the
   same way, and the step remains open.
3. **Given** a UI-native intent that fails validation, **When** the tap is
   submitted, **Then** the error surfaces directly to the user (no LLM
   retry path exists for this case) and no partial write occurs.
4. **Given** a step marked complete via a UI tap, **When** the user later
   opens a conversation about that skill, **Then** the coach is aware of it
   exactly as it would be for a conversationally recorded check-in — nothing
   downstream distinguishes the two once recorded, beyond the `source` tag.

---

### Edge Cases

- Multiple check-ins for the same step on the same day → all recorded; derived
  metrics count practice sensibly (no double-crediting a streak day). Streak is
  defined as consecutive calendar days with at least one check-in for that
  skill, so same-day duplicates count once toward the streak.
- User reports practice from days ago ("I swam twice over the weekend") → check-ins
  recorded with the stated past timestamps, and cadence/streaks recompute
  accordingly.
- "Behind cadence" threshold: no check-in within 1.5× the expected interval for
  any active step triggers a nudge.
- Notification fatigue: max 1 nudge per skill per day, max 3/week, sent in
  user's local daytime.
- User with multiple skills behind simultaneously → nudges are consolidated or
  spaced, never a burst of notifications at once.
- Timezone handling for cadence math and send windows → user's local timezone,
  captured at signup and updatable.
- Deep link fires when the user is signed out or the skill was deleted → app routes
  to sign-in / a safe fallback screen, never a crash.
- User taps "mark complete" twice in quick succession (double-tap) → the intent
  pipeline's idempotency and validation handle it the same way a duplicate
  conversational check-in would; no double-crediting.
- A stale goal's "start new pursuit" option is chosen → this simply begins the
  feature 002 wizard for a new skill; the stale goal is untouched, still open,
  still visible on the dashboard.
- Dashboard is opened while offline → shows the last-loaded state with a clear
  stale-data indicator, consistent with the network-failure handling
  established in feature 001 (FR-007-equivalent for reads).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Users MUST be able to record check-ins conversationally (voice or
  chat); each check-in captures step, timestamp, outcome, sentiment, and optional
  obstacle, via the typed-intent pipeline (`log_checkin`, `report_obstacle`,
  `complete_step`) (Constitution I).
- **FR-002**: The coach MUST respond to check-ins with specific acknowledgement:
  celebration for progress, a concrete workaround or adjustment for obstacles.
- **FR-003**: Step completion MUST be recordable in conversation and MUST be
  reflected in the plan view and progress view.
- **FR-004**: All progress metrics (completed steps, streaks, cadence adherence)
  MUST be derived on demand from check-in records; no stored counters
  (Constitution II).
- **FR-005**: Each skill MUST have a progress view showing completed steps,
  streak (consecutive calendar days with at least one check-in for that
  skill), and cadence adherence.
- **FR-006**: Session end MUST trigger an automatic summary stored against the
  session; the definition of "session end" MUST include abandoned conversations
  — a configurable inactivity timeout (default: 30 minutes) — not only explicit
  goodbyes.
- **FR-007**: New sessions MUST include the last N session summaries in the
  coach's context, where N is configurable (default: 5).
- **FR-008**: A plan's cadence expectations MUST be recorded in the notification
  schedule at plan creation/revision time, and a daily scan MUST identify
  behind-cadence users — no check-in within a configurable multiplier of the
  expected interval (default: 1.5×) for any active step — and send each a push
  notification.
- **FR-009**: Notifications MUST deep-link to the specific skill's session
  (scheme `skillcoach://`, reserved since 001; pattern
  `skillcoach://skill/{id}/session`), and the coach's opening MUST reference the
  specific gap (missed step, elapsed time).
- **FR-010**: Notification sending MUST respect OS permission state, a
  configurable frequency cap (default: max 1 nudge per skill per day, max 3 per
  week) and configurable quiet hours (default: restrict sends to the user's
  local daytime), and MUST log delivery outcomes.
- **FR-011**: Users MUST be able to revise their goal conversationally
  (`revise_goal`); revisions create superseding goals, preserving history
  (Constitution III). Any plan regenerated after a goal revision links to the new
  goal; prior plans keep pointing at the goals they served (schema approved
  2026-07-12).
- **FR-012**: Summaries MUST use the cheap model tier; all new AI calls in this
  feature go through the budgeted queue (Constitution V).
- **FR-013**: Push tokens MUST have a managed lifecycle: registered when
  notification permission is granted, refreshed when the platform rotates them,
  revoked on sign-out, and supporting multiple devices per user (each device its
  own token; a nudge goes to all active tokens).
- **FR-014**: On sign-in, the system MUST present a home dashboard showing
  every skill the user pursues as a card (goal as parent, active plan as
  child), reflecting the same derived progress as that skill's dedicated
  progress view (FR-005). A stale goal (no check-in activity within a
  configurable threshold, default: 14 days) MUST be visibly marked and offer
  continue, revise-via-conversation, or start-new; it MUST NOT offer deletion.
- **FR-015**: A plan step MUST be completable directly via a UI-native tap —
  full completion constructs a `complete_step` intent, partial progress
  constructs a `log_checkin` intent — both bypassing the LLM entirely. These
  intents MUST validate against the same Pydantic schemas and apply through
  the same deterministic translator as LLM-produced intents (Constitution I).
  A UI-native intent that fails validation MUST surface the error directly to
  the user (no LLM retry path applies to this case).
- **FR-016**: Every CheckIn MUST record its `source` (`conversation` |
  `ui_tap`) so provenance is auditable, without affecting how progress is
  derived (Constitution II treats both sources identically).
- **FR-017**: No UI element MUST be able to delete or terminally end a goal
  or its plan (Constitution III). Ending a pursuit is not a feature of this
  system in v1 — goals persist indefinitely as standing reminders.
- **FR-018**: Every tunable threshold introduced by this feature — session
  inactivity timeout (FR-006), session-summary count N (FR-007), cadence
  multiplier (FR-008), notification frequency cap and quiet hours (FR-010),
  and stale-goal threshold (FR-014) — MUST be defined as a single named
  constant in one central module (not environment variables — these are
  rare-to-change tuning parameters, not secrets or per-deploy values), so
  each is defined once and referenced everywhere it's used rather than
  hardcoded inline at each call site.

### Key Entities

- **CheckIn**: A practice record — step, timestamp, outcome, sentiment,
  optional obstacle, and `source` (`conversation` | `ui_tap`, schema approved
  2026-07-13). Append-only; the sole source of progress truth regardless of
  source.
- **Session**: One conversation; holds its end-of-session summary and timestamps.
- **Session summary**: Concise account of a session (topics, check-ins, obstacles,
  commitments) used as future context.
- **Cadence schedule**: Relational record of each user's expected practice rhythm
  per step/plan, written at plan creation/revision; input to the daily scan
  (Constitution VII — lives in the relational store).
- **Notification record**: What nudge was sent, when, to whom, for which skill, and
  the delivery outcome.
- **Push token**: A registered device's push token, one row per device, with a
  managed lifecycle (registered, refreshed on rotation, revoked on sign-out;
  FR-013).
- **Goal (revision)**: As in feature 002; this feature adds the superseding-revision
  flow.
- **Home dashboard**: Not a stored entity — a read-only aggregation of every
  skill the user pursues plus each one's derived progress, rendered as
  cards. No new node type; assembled from existing Skill/Goal/Plan/CheckIn
  data at request time.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: End-to-end loop demonstrable: a user goes behind cadence → receives
  exactly one push → taps it → lands in the right skill's session → the coach's
  opening references the specific missed step → a check-in recorded in that session
  updates the progress view.
- **SC-002**: Progress math is provably derived: deleting no data and recomputing
  from check-ins always reproduces displayed metrics; hand-computed fixtures match
  in automated tests.
- **SC-003**: In a multi-session test script, the coach references at least one
  correct fact from a prior session in 100% of new sessions without user recap.
- **SC-004**: No user receives notifications exceeding the agreed frequency cap, and
  on-cadence users receive zero nudges, verified over a simulated multi-week run.
- **SC-005**: Goal revision preserves history: after two revisions, all three goals
  are retrievable in order.
- **SC-006**: The home dashboard and each skill's dedicated progress view
  always agree, for any user and at any time — both are queries over the
  same CheckIn data, never a separately cached value.
- **SC-007**: Marking a step complete or partial via the dashboard makes zero
  LLM calls (verified in logs/usage accounting) and updates the dashboard
  and progress view immediately.

## Assumptions

- Check-ins are self-reported and trusted; no sensor/integration verification in v1.
- Cadence scanning is daily-resolution; intra-day scheduling precision is not
  required for v1 nudges.
- Push notifications require the mobile apps; web users get gap-awareness in-session
  only.
- Sentiment is captured coarsely (e.g., positive/neutral/negative) as part of the
  check-in intent schema; fine-grained emotion analysis is out of scope.
- Encouragement/celebration tone is prompt-level behavior, acceptance-tested by
  script review rather than hard metrics.
- "Reschedule" a goal's timeline or effort happens via conversation
  (`revise_goal`), not a raw edit form on the dashboard — goal-level changes
  stay conversational by design; only step-level completion is UI-native.
- The home dashboard is read/tap-only in v1 — no drag-to-reorder, no bulk
  actions, no separate CRUD screens beyond the tap-to-complete affordance.
