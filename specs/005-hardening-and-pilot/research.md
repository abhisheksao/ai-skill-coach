# Research: Hardening & Pilot (005)

**Date**: 2026-07-18 | **Input**: [spec.md](spec.md) | **Constitution**: v1.8.0

Each entry: Decision / Rationale / Alternatives considered. Live-console
verifications demanded by FR-011 are listed at the end and re-checked in
quickstart.md — never trusted from this document alone (Constitution
workflow rule).

---

## R1. Rate-limit queue: replace `BudgetGuard` internals, keep `acquire`

**Decision**: Implement the real Constitution-V queue inside the existing
seam. `BudgetGuard.acquire(user_id)` (001's v0 stub, whose docstring
already promises exactly this replacement) becomes the front door to a new
`LlmQueue`: a process-local FIFO admission gate (asyncio semaphore sized
by `constants.LLM_MAX_CONCURRENT`) plus a provider-level token bucket
(`constants.LLM_MAX_RPM`) that *delays* rather than rejects when the
provider rate is near, while per-user daily budgets stay in Postgres via
the existing `increment_llm_usage` RPC. Provider 429/5xx backoff stays
where it already lives (tenacity inside `LlmService`) — the queue paces
admissions; tenacity handles the residual failures. A new `user_limits`
table adds a per-user `daily_budget_override` and a `blocked` flag — the
kill switch / per-user blast-radius cap the spec's cost-spike edge case
requires — consulted in the same `acquire` call.

**Rationale**: Call sites (`chat.py`, session summarize) already call
`acquire` before every LLM call; keeping the interface means zero changes
at call sites and no chance of an unbudgeted path appearing. A single
always-warm host (FR-004) makes a process-local queue correct — there is
exactly one API process for the pilot, so no distributed coordination is
needed at ~100-user scale (spec Assumptions).

**Alternatives considered**: (a) External queue (Redis/celery) — new
vendor, new spend, prohibited without approval and absurd at this scale.
(b) Rejecting (429) when the provider bucket is empty — violates US1
scenario 1 ("requests queue with backoff and eventually succeed"); delay
up to `constants.LLM_QUEUE_MAX_WAIT_SECONDS`, then degrade gracefully.

## R2. Budget exhaustion becomes an in-conversation coach message

**Decision**: `POST /v1/chat` stops surfacing `BudgetExceeded` as a raw
429 error. When `acquire` raises, the route returns a normal 200 chat
response whose reply is the i18n key `errors.budget_exhausted_reply`
(friendly copy with a reset expectation), zero LLM calls made, no
assistant message persisted as coaching content (persisted like the
degraded-validation turn is today, so the transcript stays honest). The
429-with-`resets_at` error envelope remains for non-conversational
endpoints. The client renders the reset time from a new `resets_at`
field (UTC midnight of the budget day, same boundary `llm_usage` uses).

**Rationale**: US1 scenario 2 says "clear, kind **in-conversation**
explanation" — an HTTP error toast is not in-conversation. Reusing the
degraded-turn pattern (llm.py already returns reply-only ChatTurns on
validation exhaustion) keeps one shape for "the coach can't fully help
right now."

**Alternatives considered**: keep 429 and have the client fake a bubble —
splits the logic across platforms and leaves other clients (future) raw.

## R3. Paid-tier switch is a key swap; verified config-only

**Decision**: Create a Google Cloud project with billing enabled, mint a
new Gemini API key under it, and set it as `GOOGLE_API_KEY` on the host —
no code change (Constitution VI; `config.py` already isolates key + model
name). The old free-tier (AI Studio) key is removed from the deploy
environment the same day so it cannot serve pilot traffic (US2
scenario 1). Paid-tier Gemini API traffic is not used for training under
Google's paid-services terms — the privacy property US2 requires.

**Rationale**: The provider abstraction was built for exactly this
(Constitution VI); the switch is the proof it worked.

**Alternatives considered**: switching provider entirely — out of scope,
nothing in the spec requires it, and quotas on paid Gemini are ample for
~100 users.

## R4. Warm host = Render Starter; a one-line blueprint change

**Decision**: Change `render.yaml` `plan: free` → `plan: starter`
(~$7/mo), the first sanctioned spend (Constitution IX names it;
FR-004 approves it). Same service, same secrets, same health check;
Render Starter never spins down.

**Rationale**: The blueprint already exists and encodes everything else;
minimum-diff migration with no new vendor.

**Alternatives considered**: Fly.io/Railway — new vendor for no benefit;
keep-alive-pinging the free tier — Render free spins down on idle
regardless of pings' reliability, and cold starts are explicitly
unacceptable for voice (FR-004).

## R5. Nightly export via GitHub Actions → Supabase Storage

**Decision**: A scheduled GitHub Actions workflow
(`.github/workflows/nightly-export.yml`, cron nightly) runs a new
standalone script `api/scripts/export_graph.py` (Neo4j Python driver;
Neo4j + Supabase secrets from GH repo secrets) that serializes the entire
coaching graph — all nodes and relationships, per the fixed v1 schema —
to a dated JSON artifact and uploads it to a **private** Supabase Storage
bucket `graph-exports`. A companion `api/scripts/restore_graph.py`
replays an export into an empty instance. The workflow failing (export
error, upload error, or a final freshness assertion) triggers GitHub's
built-in workflow-failure email to the repo owner — that is the
missed-export alert (FR-005). The nightly export doubles as the Aura
keep-alive touch (Aura Free pauses after ~3 idle days — dev-plan risk
table).

**Rationale**: Running the export *outside* the API host means backups
still happen when the backend is broken — the exact scenario backups
exist for. GitHub and Supabase are both existing vendors (no Constitution
approval gate); Supabase Storage free tier (1 GB) holds years of pilot-
scale JSON exports; access control is the service-role key (spec edge
case: exports are access-controlled).

**Alternatives considered**: (a) Export endpoint on the API triggered by
pg_cron — dies with the backend, and pg_net POST bodies can't stream a
dump out anywhere durable. (b) GH Actions artifacts as storage — 90-day
retention and repo-visibility coupling; storage should outlive CI
plumbing. (c) Aura's own backups — not available on Free tier (verified
motivation for this whole requirement).

## R6. Alert channel = GitHub Actions failure email, three workflows

**Decision**: All three required alerts ride the same mechanism — a
scheduled workflow that **fails loudly** when its check fails, producing
GitHub's failure email (spec Assumptions allow lightweight email
alerting): (1) `nightly-export.yml` (R5); (2) `healthcheck.yml` — every
30 min, curl the deployed `/health`, fail on non-200 (also catches the
warm host dying); (3) `spend-check.yml` — daily, runs
`api/scripts/spend_check.py` against the usage views and fails when
daily estimated spend crosses `SPEND_ALERT_THRESHOLD_USD` (a workflow
env value, operator-tunable without a deploy) — FR-003's threshold
alert. Each workflow is deliberately failed once during validation to
prove the email arrives ("reliable **and tested**", spec Assumptions).

**Rationale**: One mechanism, zero new vendors, zero spend, arrives even
when the product is fully down.

**Alternatives considered**: transactional-email vendors (Resend etc.) —
new third-party, needs approval, adds a secret; Expo push to the
operator's own device — dies exactly when the backend dies.

## R7. Cost visibility: token columns on `llm_usage` + SQL views

**Decision**: Extend `llm_usage` with `prompt_tokens`, `output_tokens`
(accumulated per user-day via an extended `increment_llm_usage` RPC —
the queue reports actuals from LangChain's `usage_metadata` after each
call). A migration adds operator SQL **views**: `ops_daily_spend`
(per-day tokens × per-model rates from a `model_rates` reference table
seeded by the migration → estimated USD), `ops_user_daily_usage`
(per-user calls/tokens). The operator cost view (US1 scenario 3) is
these views in the Supabase dashboard SQL editor — dashboards, no SSH
(US4), documented in `docs/runbooks/operations.md`.

**Rationale**: Estimated-from-tokens spend is auditable and available
per-user (billing consoles aren't per-user); rates live in a table so a
price change is an UPDATE, not a deploy.

**Alternatives considered**: scraping Google billing — no API worth the
effort at this scale; a bespoke operator web UI — pure scope creep for a
1-operator pilot when SQL views answer every SC-005 question.

## R8. Analytics: server-side `analytics_events` table + views

**Decision**: A new Postgres table `analytics_events`
(pseudonymous `user_sub`, `event_type`, `properties` jsonb, timestamp) —
written **server-side only** by a tiny `AnalyticsService` at the seams
that already see the events: session summarized → `session_ended`
(session_summary service), first message of a session → `session_started`
(chat route), validation-retry exhaustion → `intent_validation_failed`
(llm service seam via chat route), push outcome → `push_sent`/
`push_failed` (notifications service, mirroring the existing delivery
log). Views compute daily session counts, retention (distinct active
subs day-over-day), and intent-validation failure rate — SC-005's three
numbers. Properties never contain message bodies (FR-007). Analytics
writes are fire-and-forget: an analytics failure never fails the user
request.

**Rationale**: Every required metric originates in the backend, so no
client SDK, no new endpoint, no consent surface, no third-party
(PostHog etc. would need Constitution approval). Postgres is the
constitution-VII home for non-graph operational data.

**Alternatives considered**: deriving everything from existing tables
without an events table — retention and failure-rate queries get
fragile and slow to answer "within minutes" (SC-005); a client-side
analytics SDK — overkill and a privacy surface the pilot doesn't need.

## R9. Voice failure matrix (FR-006) — cells and states

**Decision**: The agreed matrix, each cell → a named UI state with
specific copy (i18n, 5 languages) and an always-available chat path:

| # | Condition | Detection | State/remedy shown |
|---|-----------|-----------|--------------------|
| V1 | Mic permission never granted / denied | existing (003) | existing `permissionDeniedGuidance` — re-verify |
| V2 | Permission revoked **mid-session** | recognizer error on next press | same guidance state, mid-session path tested |
| V3 | Recognizer unavailable (no engine / unsupported) | existing `voice-capabilities` probe | existing `unavailableGuidance` — re-verify |
| V4 | Offline / network lost before send | fetch failure / NetInfo | composer keeps text; message marked **failed** with retry; auto-send on reconnect (US3 scenario 2) |
| V5 | Network lost **mid-recognition** | recognizer `network` error | interim transcript preserved into the composer; specific "connection lost" state |
| V6 | TTS unavailable / fails to speak | `Speech` error callback | silent-with-banner state: reply still shown as text, spoken-replies toggle marked unavailable |
| V7 | Audio focus lost (call, other app) | recognizer aborted/interruption error | session stops cleanly, partial transcript preserved, "resume when ready" state |

Chat input remains enabled in every cell — no state may disable the text
composer.

**Rationale**: 003 built V1/V3 happy-path fallbacks; V2/V4–V7 are the
"remaining gaps strangers will find" the spec names. Enumerating cells
here makes FR-006 testable (each cell = at least one automated test +
one manual-matrix row in docs/testing.md).

**Alternatives considered**: a generic "voice error" state — exactly the
dishonest dead-end US3 forbids ("names the problem and the remedy").

## R10. Pilot latency target (resolves the spec's NEEDS CLARIFICATION)

**Decision**: Adopt the spec's own proposal: **p90 time-to-reply-start
< 3 s** on a warm host, measured from request arrival to response
readiness using the existing request log's `duration_ms` on
`POST /v1/chat` (reply start ≈ response complete for the non-streaming
API; if p90 total < 3 s, reply start meets it a fortiori). Verified over
a pilot day via a documented SQL/log query, not a one-off stopwatch.

**Rationale**: The proposal was already socialized in the spec; the
existing structured log makes it measurable with zero new
instrumentation.

**Alternatives considered**: streaming responses to cut perceived
latency — real work, not required to meet 3 s with Flash-Lite class
models on a warm host; revisit only if measurement fails the target.

## R11. Beta distribution: local builds uploaded to TestFlight / Play internal

**Decision**: Keep the no-EAS-Build posture (001 FR-008): iOS — local
Xcode archive → App Store Connect upload → TestFlight internal testing
(requires Apple Developer Program, ~$99/yr, already flagged in
`docs/getting-started.md`); Android — local `gradlew bundleRelease` AAB →
Play Console internal track ($25 one-time, flagged). Both procedures are
written as `docs/runbooks/release.md` and executed at least once before
invites. **Sign in with Apple** is added to the auth screen (Supabase
Apple provider + `expo-apple-authentication`) because App Store review
requires it once Google login ships through TestFlight — this is the
005-gate item getting-started already flags.

**Rationale**: EAS Build stays off (existing decision, no new
subscription); both store fees are pre-flagged spend awaiting the
human's go at execution time (Constitution IX — the *tasks* build the
runbooks and app changes; the human performs the paid enrollments).

**Alternatives considered**: EAS Build free tier — quota-limited and a
new build dependency mid-hardening; skipping Sign in with Apple — a
predictable TestFlight review rejection.

## R12. Onboarding for unassisted first use

**Decision**: A first-run explainer step in the existing `(onboarding)`
group after profile setup: 2–3 swipeable cards covering push-to-talk
("hold to speak") and what notifications do; permission prompts stay
**contextual** — mic permission is requested on first mic-button press
(003 behavior, kept), notification permission is requested from the
explainer card's "enable nudges" action rather than an unexplained
system dialog at launch. Skippable; never shown again after completion
(flag in AsyncStorage + profile).

**Rationale**: US5 scenario 2 verbatim; contextual permission requests
measurably beat cold launch-time dialogs and match how 003/004 already
request mic/push.

**Alternatives considered**: video/interactive tutorial — pilot overkill.

## R13. Deletion entry point + operator deletion runbook

**Decision**: A "Delete account" row in Settings opens
`EXPO_PUBLIC_DELETE_ACCOUNT_URL` (client env/config — URL swap only,
per the spec's resolved edge case) in the system browser; placeholder
page now, static policy page later. Actual deletion during the pilot is
operator-executed per `docs/runbooks/deletion.md`: delete the user's
Neo4j subgraph (single parameterized detach-delete scoped to the user id,
run by an operator script `api/scripts/delete_user.py`), Supabase auth
user + rows (messages, usage, tokens, notifications, analytics via
cascade or explicit deletes), and their slices of any stored exports'
future runs (past exports age out; documented in the runbook per the
spec's backup-retention edge case).

**Rationale**: Matches the 2026-07-12 resolution recorded in the spec;
Apple permits web-completed deletion reached from in-app.

**Alternatives considered**: full in-app self-service deletion — spec
explicitly defers it past the pilot.

## R14. Logging policy graduates (FR-007)

**Decision**: Codify what `logging_setup.py`'s docstring promised for
005: structured JSON only; **never** message/transcript bodies, tokens,
or secrets; user identity only as the pseudonymous `sub`. AI failures
get a dedicated structured event (endpoint, sub, intent type, failure
class) at the llm/chat seam so US4 scenario 2 is answerable from logs.
A unit test asserts redaction: log records produced during a chat turn
with a known sentinel string in the message never contain the sentinel.
The policy text lives in `docs/runbooks/operations.md`.

**Rationale**: The mechanism exists; 005 owes the policy, the AI-failure
event, and the proof.

**Alternatives considered**: a log-shipping vendor — Render's built-in
log view is searchable and $0; nothing in US4 needs more.

## R15. External-limit live verification (FR-011) — the checklist

Verified in consoles before pilot start (recorded in quickstart.md when
executed, per the Constitution's live-verification rule):

1. Gemini **paid-tier** quotas (RPM/RPD for the pinned model) in the
   Google Cloud console — not the free-tier numbers from 001.
2. Neo4j Aura Free node/relationship ceiling for the Aura instance
   (docs conflict 50K vs 200K — read the console number) + current
   counts; weekly review row added to `docs/runbooks/operations.md`.
3. Supabase free-tier: storage quota (exports bucket), pg_cron/pg_net
   still enabled, DB size.
4. Expo push service: no hard published cap, but confirm current
   throughput terms.
5. Render Starter: confirm always-on (no idle spin-down) post-upgrade.

---

## Resolved clarification

The spec's single `[NEEDS CLARIFICATION]` (pilot latency target) is
resolved by R10: **p90 reply start < 3 s warm**, adopted 2026-07-18.
The spec's edge-case line is updated to record this.
