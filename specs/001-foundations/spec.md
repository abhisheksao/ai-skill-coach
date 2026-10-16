# Feature Specification: Foundations

**Feature Branch**: `001-foundations`

**Created**: 2026-07-11

**Status**: ✅ Complete (2026-07-13) — see quickstart.md results; iOS device
validation deferred, all else verified

**Input**: User description: "Users can create an account, sign in on iOS/Android/web, and exchange a text message with an AI that responds. New signups are represented in the coaching graph."

## Clarifications

### Session 2026-07-12

- Q: Which sign-in methods should feature 001 support at launch? → A: Email/password
  + Google OAuth. Sign in with Apple deliberately deferred; it becomes a hard gate
  in feature 005 before TestFlight distribution (App Store rule when third-party
  login is offered).
- Q: Repo layout for the app and API code? → A: Monorepo in this repository —
  `app/` (client) and `api/` (backend) beside `specs/` and `docs/`.
- Q: What should the signup profile capture? → A: Auto-detected device timezone
  (silently captured, user-updatable) plus a post-signup profile step with two
  inputs: preferred language (picker, pre-selected from device locale — added with
  Constitution X, 2026-07-12) and an optional display name; nothing else.
- Q: (gap review) Message grouping from day one? → A: yes — messages carry a
  session identifier and a nullable skill scope so 002/004 need no migration.
- Q: (gap review) When is the coaching-graph user created? → A: on completion of
  the post-signup profile step (language + optional name + consent checkbox);
  before that, nothing is saved.
- Q: (gap review) Streaming responses? → A: plain request/response chat for the
  initial dev build; revisit before feature 003.
- Q: (gap review) LLM budget in 001 vs the 005 queue? → A: v0 in 001 = per-user
  daily counter + retry/backoff, swappable for the 005 queue.
- Q: (gap review) App CI? → A: none — local Expo dev builds only (no EAS).
  Backend CI initially kept, then deferred too (2026-07-12, PAT workflow-scope
  friction; revisit at 005): all checks run locally.
- Q: (gap review) Apple Developer license? → A: deferred (flagged spend); needed
  at 004 for iOS push. Free provisioning until then (7-day build expiry accepted).
- Q: (gap review) Deep-link scheme? → A: reserve `skillcoach://` in the 001
  scaffold; routes (e.g. `skillcoach://skill/{id}/session`) built at 004.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Create an account and sign in (Priority: P1)

A new user installs the app (or opens the web version), creates an account with email
and password or a supported OAuth provider, and signs in. On subsequent launches their
session is remembered until they sign out.

**Why this priority**: Nothing else in the product is possible without an
authenticated identity; every later feature keys coaching state to the user.

**Independent Test**: Can be fully tested by creating an account on one platform,
signing out, signing back in, and confirming the same identity is restored — with no
chat functionality present at all.

**Acceptance Scenarios**:

1. **Given** a fresh install with no account, **When** the user signs up with a valid
   email and password, **Then** an account is created and the user lands in the app
   signed in.
2. **Given** an existing account, **When** the user signs in with correct credentials
   on iOS, Android, or web, **Then** they are authenticated and see the same identity
   on each platform.
3. **Given** a signed-in user, **When** they close and reopen the app, **Then** they
   remain signed in without re-entering credentials.
4. **Given** invalid credentials, **When** the user attempts to sign in, **Then** a
   clear error is shown and no session is created.

---

### User Story 2 - Exchange a text message with the AI (Priority: P2)

A signed-in user types a message into a chat screen, sends it, and receives an
AI-generated response rendered in the conversation.

**Why this priority**: This proves the full round trip — client → backend → AI →
client — that every coaching interaction will ride on. It is the heartbeat of the
architecture.

**Independent Test**: Sign in, send "hello", and observe a coherent AI reply rendered
in the chat; verify both the user message and the reply are persisted and reload with
the conversation.

**Acceptance Scenarios**:

1. **Given** a signed-in user on the chat screen, **When** they send a text message,
   **Then** an AI response is rendered in the conversation within an acceptable wait
   (loading state shown while pending).
2. **Given** a sent message, **When** the conversation is reloaded later, **Then**
   both the user's message and the AI's reply are still present.
3. **Given** the AI service is unreachable, **When** the user sends a message,
   **Then** the user sees a friendly failure state and can retry; the app does not
   crash or hang.

---

### User Story 3 - New signups enter the coaching graph (Priority: P3)

When a user completes the post-signup profile step (language, optional name,
consent), the coaching system creates a corresponding user record in the structured
coaching state, ready to be linked to skills, goals, and plans in later features.
Until that step completes, nothing is saved.

**Why this priority**: Invisible to the user today, but every later feature (skills,
plans, check-ins) attaches to this record; creating it at the earliest meaningful
moment avoids migration work later.

**Independent Test**: Sign up a fresh account, complete the profile step, and
verify, via an admin/query check, that exactly one coaching-graph user record
exists for that identity.

**Acceptance Scenarios**:

1. **Given** a completed post-signup profile step, **When** the coaching state is
   inspected, **Then** exactly one user record exists for that account, keyed to
   the auth identity.
2. **Given** a profile step whose coaching-record write fails (auth exists, graph
   write lost), **When** the user next authenticates, **Then** the system
   reconciles by creating the missing coaching record (no duplicates, no orphans).
3. **Given** a user who signs up but abandons the profile step, **When** they next
   launch the app, **Then** the profile step is presented again and no coaching
   record exists until it completes.

---

### Edge Cases

- Duplicate signup with an email that already has an account → clear "account exists"
  path to sign-in, no second coaching record.
- Backend cold start (free-tier host asleep) → first request may take tens of
  seconds; the client shows a persistent loading state rather than timing out
  silently. (Accepted for dev per Constitution IX.)
- User loses connectivity mid-send → message send fails visibly and is retryable;
  no phantom duplicate messages after retry.
- Sign-out clears local session state; another user signing in on the same device
  sees only their own conversation.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow account creation with email + password and with
  Google OAuth. Sign in with Apple is deferred by decision (2026-07-12) and MUST be
  added before iOS TestFlight distribution in feature 005 — offering Google login
  on iOS without Apple sign-in fails App Store review.
- **FR-002**: Users MUST be able to sign in and sign out on iOS, Android, and web
  with the same account.
- **FR-003**: Sessions MUST persist across app restarts until explicit sign-out or
  expiry.
- **FR-004**: Signed-in users MUST be able to send a text message and receive an
  AI-generated reply rendered in a conversation view.
- **FR-005**: All messages (user and AI) MUST be persisted with sender, timestamp,
  a `modality` attribute (value `chat` for this feature, per Constitution IV), a
  session identifier grouping the conversation, and an optional skill scope (null
  until skills exist in feature 002) — so features 002/004 inherit no
  message-table migration.
- **FR-006**: Completing the post-signup profile step (FR-011) MUST create exactly
  one user record in the structured coaching state, linked to the auth identity;
  creation MUST be idempotent and reconciled on a later sign-in if the initial
  write fails. Until the profile step completes there is nothing to save and no
  coaching record exists; an abandoned profile step is re-presented at next
  launch.
- **FR-007**: AI-service failures MUST surface as a user-visible, retryable error
  state; they MUST NOT lose the user's typed message.
- **FR-008**: No CI pipeline in this phase (decision 2026-07-12, API CI deferred
  2026-07-12 during implementation): lint and tests for both codebases run
  locally (`uv run ruff check . && uv run pytest` for api; `npm run lint` /
  `npm test` for app); local Expo dev builds only (no EAS). Revisit CI at
  feature 005.
- **FR-009**: All AI calls MUST pass through a v0 budget guard from day one
  (Constitution V): a per-user daily call counter plus retry-with-backoff. The
  full rate-limit queue arrives in feature 005; v0 MUST be swappable for it
  without touching call sites.
- **FR-010**: At signup, the system MUST capture the device's timezone automatically
  (stored on the profile, user-updatable later — feature 004's cadence reminders
  depend on it) and MAY collect an optional display name; no other profile fields
  are collected at signup.
- **FR-011**: Immediately after signup, a lightweight profile step MUST ask for
  the user's preferred language (an explicit picker, pre-selected from the device
  locale, English fallback if unsupported) alongside the optional display name of
  FR-010; both remain changeable later. The app UI and AI replies MUST render in
  the preferred language for all launch languages (EN, HI, ES, FR, DE —
  Constitution X).
- **FR-012**: The profile step MUST include a consent acknowledgment (checkbox)
  linking to a privacy/data-use page at a configurable URL (generic placeholder
  page now; real static policy page later — URL swap only).
- **FR-013**: The app scaffold MUST register the `skillcoach://` deep-link scheme
  (decision 2026-07-12); routes arrive with feature 004 (pattern:
  `skillcoach://skill/{id}/session`).

### Key Entities

- **User (auth)**: The authenticated identity — email, provider (email/password or
  Google), credentials. Its profile carries an auto-detected, updatable timezone,
  a preferred language (Constitution X), and an optional display name. Lives in
  the relational store (Constitution VII).
- **User (coaching graph)**: The coaching-state representation of the same person;
  root for future Skill/Goal/Plan attachments. Lives in the graph (Constitution VII).
- **Message**: One utterance in a conversation — sender (user/assistant), text,
  timestamp, modality, session identifier, optional skill scope. Lives in the
  relational store; never in the graph.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A brand-new user can go from app open to seeing an AI reply on a
  physical iOS device, a physical Android device, and a desktop web browser.
- **SC-002**: 100% of completed profile steps produce exactly one coaching-graph
  user record (verified by automated test and by inspection during acceptance).
- **SC-003**: Messages persist: killing and reopening the app shows the prior
  conversation intact.
- **SC-004**: Lint and tests pass locally for both codebases, and a teammate can
  bring up the full stack from the README alone (secrets excepted).
- **SC-005**: Running cost for this feature is $0/month (Constitution IX).

## Assumptions

- Free-tier backend hosting with cold starts (30–60 s after idle) is acceptable for
  this phase; no warm host until feature 005.
- The AI reply at this stage needs no coaching intelligence — a simple conversational
  response proves the pipeline.
- Native device builds (not the store-review path) are sufficient; TestFlight/Play
  tracks arrive in feature 005.
- The app and API live in this repository as a monorepo — `app/` (client) and
  `api/` (backend) beside `specs/` and `docs/`.
- Chat is plain request/response (no streaming) in this phase — kept simple by
  decision; revisit before feature 003, where voice latency may force streamed
  replies.
- Push notifications are out of scope until 004; the paid Apple Developer account
  (~$99/yr) and the Firebase project for FCM credentials are deferred with them
  (flagged spend, deferred 2026-07-12). Free-provisioned iOS dev builds expire
  every 7 days — accepted friction.
- Voice is out of scope (feature 003); this feature is text-only, but the message
  record already carries the modality attribute so voice adds no schema change.
- Messages carry a session identifier from day one, but Session nodes in the graph
  are created only from feature 004 — until then the identifier has no graph
  counterpart, by design.
