# Feature Specification: Hardening & Pilot

**Feature Branch**: `005-hardening-and-pilot`

**Created**: 2026-07-11

**Status**: Draft

**Input**: User description: "The product is reliable, private, recoverable, and observable enough for ~100 strangers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Heavy use never breaks the product or the budget (Priority: P1)

A pilot user (or a burst of them) uses the coach intensively. AI calls queue and
retry transparently; a user who exhausts their daily allowance gets a friendly
explanation, not an error; total spend stays visible and bounded for the operator.

**Why this priority**: Uncontrolled AI usage is the one failure mode that is both
user-facing (hard errors) and operator-facing (surprise bills); it gates putting
strangers on the product at all.

**Independent Test**: Drive scripted load past provider rate limits and past one
user's daily budget; verify no user-visible hard failures, correct friendly
budget-exhausted messaging, and accurate usage accounting.

**Acceptance Scenarios**:

1. **Given** provider rate limits are hit, **When** users send messages, **Then**
   requests queue with backoff and eventually succeed or degrade gracefully — no raw
   provider errors reach users.
2. **Given** a user reaches their daily AI budget, **When** they send another
   message, **Then** they receive a clear, kind in-conversation explanation and a
   reset expectation; other users are unaffected.
3. **Given** the operator opens the cost view, **When** usage occurs, **Then**
   per-day spend and per-user call counts are visible, and an alert fires when spend
   crosses a configured threshold.

---

### User Story 2 - User data is private and recoverable (Priority: P1)

Pilot users' conversations and coaching state are handled under commercial-grade
terms (no training on their data), and the operator can restore coaching state from
a recent backup after a data-loss event.

**Why this priority**: Real strangers' data creates real privacy and durability
obligations; the free-tier terms and no-backup posture that were fine for dev are
not acceptable for a pilot.

**Independent Test**: Verify the AI provider account is on the paid/commercial tier
via configuration only (zero code change); run the restore runbook against a fresh
graph instance from last night's export and confirm coaching state is intact.

**Acceptance Scenarios**:

1. **Given** the tier switch to paid AI service, **When** it is performed, **Then**
   it is configuration/secrets only (Constitution VI) and dev free-tier keys no
   longer serve pilot traffic.
2. **Given** nightly export is enabled, **When** any night passes, **Then** a dated
   coaching-state export exists in durable storage, and a missed export raises an
   alert.
3. **Given** the restore runbook, **When** it is executed against an empty instance,
   **Then** coaching state is restored and spot-checks match the source; the runbook
   has been fully executed at least once before pilot start.

---

### User Story 3 - Voice failure states are honest (Priority: P2)

Wherever voice can fail in the wild — no mic permission, recognizer unavailable,
offline, audio focus lost — the user sees an honest, specific state with a path
forward, and chat always works.

**Why this priority**: Feature 003 built the happy paths and primary fallbacks;
pilot users on unknown devices will find every remaining gap, and voice dead-ends
read as "the app is broken".

**Independent Test**: Walk a failure matrix (permission revoked mid-session,
airplane mode, recognizer missing, TTS unavailable) on both platforms; every cell
ends in a specific message and a working chat path.

**Acceptance Scenarios**:

1. **Given** any voice-failure condition from the matrix, **When** it occurs,
   **Then** the user sees a state that names the problem and the remedy, and can
   continue the same conversation by chat.
2. **Given** connectivity is lost mid-session, **When** the user acts, **Then**
   unsent input is preserved and sends on reconnect or is clearly marked failed.

---

### User Story 4 - The operator can see what's happening (Priority: P2)

The operator can answer, from dashboards/logs alone: how many sessions happened, who
is retaining, how often AI output fails validation, whether pushes deliver, and what
errored — without SSH-ing into anything during the pilot.

**Why this priority**: With ~100 strangers, issues will be reported vaguely or not
at all; observability is how the pilot produces a fixable backlog.

**Independent Test**: Generate known traffic (sessions, an intent failure, a push);
confirm each appears in analytics/structured logs with enough context to debug.

**Acceptance Scenarios**:

1. **Given** normal usage, **When** the operator reviews analytics, **Then** session
   counts, retention, and intent-validation failure rates are available per day.
2. **Given** an API error or AI failure occurs, **When** logs are searched, **Then**
   a structured entry ties it to endpoint, user (pseudonymous), and intent, without
   containing secrets or raw transcripts beyond policy.

---

### User Story 5 - Strangers can install and start unaided (Priority: P1)

An invited pilot user receives an install link through the platform's beta channel,
installs, onboards a skill, and completes sessions — with zero developer
intervention.

**Why this priority**: This is the pilot's definition; everything above serves it.

**Independent Test**: Send the beta invite to a fresh device owned by someone who
has never seen the app; observe (without intervening) install → onboarding → a
completed session.

**Acceptance Scenarios**:

1. **Given** a pilot invite, **When** the user follows it, **Then** they can
   install via the official beta channels on iOS and Android and reach onboarding.
2. **Given** the first-run experience, **When** a new user proceeds, **Then**
   onboarding explains push-to-talk and notifications, and requests permissions
   contextually.
3. **Given** the pilot cohort (initially 1–10 users), **When** the pilot window
   ends, **Then** each pilot user has completed at least 3 sessions without
   developer intervention, and top issues are triaged into a backlog.

---

### Edge Cases

- Response latency: with the always-warm backend, first token/reply must feel
  conversational. Resolved 2026-07-18 (plan research R10): target is p90 reply
  start < 3 s warm, measured from existing request logs on the chat endpoint.
- Cost spike (runaway client loop, abusive user) → per-user budget caps blast
  radius; operator alert fires; a kill switch or per-user block is available.
- Graph store nearing free-tier node limits → node counts are watched (weekly
  review), with a documented plan before the ceiling.
- Backup contains personal data → exports are access-controlled and covered by the
  same retention/deletion expectations as the primary store.
- A pilot user requests account/data deletion → resolved 2026-07-12: the app gets
  an in-app "Delete account" entry that opens a web page at a configurable URL
  (generic placeholder now; static deletion-policy/instructions page later — URL
  swap only). Actual deletion executes via operator runbook during the pilot.
  Apple permits web-completed deletion reached from in-app; full self-service is
  revisited before any public App Store release.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All AI calls MUST flow through a server-side queue with rate limiting,
  exponential backoff, and per-user daily budgets; budget exhaustion yields a
  friendly in-conversation message (Constitution V).
- **FR-002**: The AI provider MUST run on commercial/paid terms for pilot traffic
  (no training on user data); the switch MUST be config-only (Constitution VI).
- **FR-003**: Operator cost visibility MUST exist: daily spend, per-user usage, and
  a threshold alert.
- **FR-004**: The backend MUST move to an always-warm host before pilot traffic;
  cold-start delays are not acceptable for voice sessions. This is the first
  sanctioned spend (~$5–10/mo) (Constitution IX exception, human-approved).
- **FR-005**: Coaching state MUST be exported nightly to durable storage; export
  failures MUST alert; a written restore runbook MUST exist and MUST have been
  executed successfully at least once.
- **FR-006**: Every voice failure mode in the agreed matrix MUST have a specific
  user-facing state with a chat path forward.
- **FR-007**: Analytics MUST capture at minimum: session count, retention, and
  intent-validation failure rate. Backend logging MUST be structured and MUST
  exclude secrets and raw transcript bodies.
- **FR-008**: Push delivery outcomes MUST be observable (sent/failed per
  notification).
- **FR-009**: iOS and Android builds MUST be distributed through official beta
  channels (TestFlight / Play internal track), with an onboarding flow good enough
  for unassisted first use.
- **FR-010**: A pilot of 1–10 users MUST run before wider release; exit requires
  ≥3 completed sessions per pilot user without developer intervention, plus
  measured AI spend and quota headroom deemed acceptable.
- **FR-011**: External limits (AI quotas, graph node ceilings) MUST be verified
  against live consoles, not planning-document snapshots, before pilot start.
- **FR-012**: The app MUST expose an in-app account-deletion entry point opening a
  configurable policy/instructions URL; deletion itself MAY be operator-executed
  during the pilot, with a documented runbook.

### Key Entities

- **Usage record**: Per-user, per-day AI call counts and cost attribution; input to
  budgets and the cost view.
- **Export artifact**: Dated snapshot of coaching state in durable storage;
  restorable per runbook.
- **Analytics event**: Structured, pseudonymous record of product events (session
  started/ended, intent failed validation, push sent/delivered/failed).
- **Pilot cohort**: The invited users, their beta-channel status, and their session
  counts against the exit bar.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every pilot user completes ≥3 sessions with zero developer
  interventions (the feature's definition of done).
- **SC-002**: Zero raw provider errors or unhandled exceptions reach pilot users
  during the pilot window (verified from logs).
- **SC-003**: A full restore from the previous night's export succeeds on a clean
  instance, executed and documented before the first pilot invite.
- **SC-004**: Measured pilot-month cost lands within the planned envelope
  (~$15–30/mo all-in), with spend and quota headroom reviewed weekly.
- **SC-005**: The operator can produce session count, retention, and
  intent-failure-rate numbers for any pilot day within minutes, from dashboards
  alone.

## Assumptions

- ~100 users is the design ceiling for this phase; no load-balancing, sharding, or
  multi-region work is in scope.
- The pilot cohort is recruited personally (friends-of-friends scale); no public
  store listing, marketing site, or self-serve waitlist is required.
- Compliance scope is baseline privacy hygiene (commercial AI terms, access-controlled
  backups, a deletion path); formal regimes (HIPAA/GDPR representation, etc.) are
  out of scope for the pilot.
- Alerting can be lightweight (email or existing chat channel), so long as it is
  reliable and tested.
