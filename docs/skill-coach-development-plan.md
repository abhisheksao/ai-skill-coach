# Skill Coach — Phased Development Plan

> **Original plan, July 2026.** This is the document the project started from, kept
> for context. What was actually built (and where it deviated) is recorded per
> feature in [`specs/`](../specs/README.md); setup is in
> [`getting-started.md`](getting-started.md).

Voice-first skill-learning coach (swimming, running, chess, …) built on Expo React Native, FastAPI + LangChain, Gemini Flash, Neo4j Aura, and Supabase.

---

## 1. Confirmed architecture decisions

| Area | Decision | Rationale |
|---|---|---|
| Client | Expo React Native (iOS, Android, web via react-native-web); dev build required (not Expo Go) | One codebase; native voice modules need dev build |
| Voice | expo-speech-recognition (STT: SFSpeechRecognizer / Android SpeechRecognizer / Web Speech API) + expo-speech (TTS); push-to-talk | $0, on-device where supported, cross-platform incl. web |
| Chat mode | First-class alongside voice; single message pipeline with `modality` flag per message | Downstream (LLM, graph, summaries) is modality-agnostic |
| Backend | Python FastAPI + LangChain on a free host (Render free tier or similar) for dev; migrate to always-warm ~$7/mo host at Phase 4 | $0 during dev; accept cold starts (~30–60s after idle) until real users arrive |
| LLM | Gemini Flash (plans, coaching turns) + Flash-Lite (summaries, classification); LangChain structured output | Free tier for dev; cheap paid tier ($0.15/M input) at MVP |
| LLM→DB safety | LLM returns typed intents (JSON) validated by Pydantic; backend translates to parameterized Cypher. LLM never writes Cypher | Graph safety, auditability, testability |
| Graph DB | Neo4j Aura Free; nightly export to Supabase Storage (no backups on free tier) | 50K–200K node limit is ample for 100 users |
| Relational | Supabase: auth, raw transcripts, push tokens, cadence/notification schedule, pg_cron | Transcripts are relational; open-source Postgres, no lock-in |
| Notifications | expo-notifications via Expo's push service (FCM on Android, APNs on iOS), triggered by pg_cron → pg_net → an internal FastAPI endpoint | Scheduling stays in Postgres; the backend owns the logic. Android needs a Firebase project for FCM credentials |
| Skill routing | Explicit skill selection (tap skill card) in v1; free-form intent classification deferred | Saves LLM calls against free-tier daily quota |

### Graph schema (v1)

```
(:User)-[:PURSUES]->(:Skill)
(:Skill)-[:HAS_GOAL]->(:Goal)          // revisions: (:Goal)-[:SUPERSEDES]->(:Goal)
(:Skill)-[:HAS_PLAN]->(:Plan)-[:HAS_STEP]->(:Step)   // Step has order, cadence, status derived
(:Skill)-[:HAS_SESSION]->(:Session)    // one per conversation; holds LLM summary
(:Step)<-[:FOR_STEP]-(:CheckIn)        // self-reported; timestamp, outcome, sentiment, obstacle?
```

Progress is always **derived from CheckIn nodes**, never stored as a mutable counter. Goal changes create new Goal nodes so the LLM can see trajectory.

### Intent vocabulary (initial)

`create_skill`, `create_plan`, `revise_plan`, `revise_goal`, `log_checkin`, `report_obstacle`, `complete_step`, `summarize_session`. Each has a Pydantic schema; validation failure triggers retry-with-error-feedback (max 2 retries, then graceful text-only reply).

---

## 2. Phases

### Phase 0 — Foundations (≈1 week)
**Goal:** authenticated round trip: client → FastAPI → Gemini → response; one node written to Neo4j.

Deliverables:
- Monorepo (or two repos): `app/` Expo + `api/` FastAPI; CI (lint, tests) on both
- Expo dev build running on physical iOS + Android device and web
- Supabase project: auth (email + OAuth), `messages`, `profiles` tables
- Neo4j Aura Free instance; connection from API; constraint/index migration script
- Gemini API key wired through LangChain; secrets management (.env / host secrets)
- Health endpoint + minimal `/chat` echo endpoint calling Flash-Lite

Exit criteria: sign in on device → send text → LLM response rendered; `(:User)` node created on signup.

### Phase 1 — Wizard + plan generation, text-only (≈2 weeks)
**Goal:** a new user onboards a skill end-to-end via text chat.

Deliverables:
- Skill selection UI (create skill, list skills)
- Wizard conversation flow: LLM elicits current level, target achievement, timeline, weekly time budget (system prompt + conversation state machine on backend)
- Pydantic intent schemas + intent→Cypher translation layer + unit tests
- Plan generation: Goal/Plan/Step nodes created; plan review screen (steps, cadence)
- Context builder: user profile + active-skill subgraph serialized for the LLM
- JSON validation retry loop; malformed-output telemetry

Exit criteria: fresh user → "learn swimming" → wizard Q&A → plan visible in app and correct in graph; schema-invalid LLM output recovers without user-visible failure.

### Phase 2 — Voice layer (≈2 weeks)
**Goal:** full session possible voice-only on both mobile platforms.

Deliverables:
- expo-speech-recognition integration; push-to-talk button with interim transcript display
- Correction UX: editable transcript before send; "did you mean" on low confidence
- TTS playback of responses (expo-speech), interruptible (stop on new push-to-talk)
- Permissions flows (mic, speech recognition) incl. denial states
- Web: Web Speech API path verified on Chrome; graceful fallback to chat elsewhere
- `modality` flag persisted per message

Exit criteria: complete a wizard + a coaching session hands-on-mic on iOS and Android physical devices; chat mode unaffected.

### Phase 3 — Progress loop + notifications (≈2 weeks)
**Goal:** the app checks on you and the coach remembers.

Deliverables:
- Check-in conversations: `log_checkin`, `report_obstacle`, `complete_step` intents live; encouragement/workaround prompting
- Session-end summarization (Flash-Lite) → Session node; last-N summaries in context builder
- Progress UI per skill (streaks, completed steps, cadence adherence)
- Cadence table in Postgres written at plan creation; pg_cron scan → pg_net → FastAPI internal endpoint → Expo Push for behind-cadence users
- Deep link: notification → skill screen → session opens with LLM aware of gap
- Goal revision flow (`revise_goal` with SUPERSEDES)

Exit criteria: user behind cadence receives push; tapping it starts a session where the coach references the missed step; check-in updates progress UI.

### Phase 4 — MVP hardening (≈2 weeks)
**Goal:** safe to put in front of ~100 strangers.

Deliverables:
- Server-side LLM rate-limit queue, exponential backoff, per-user daily call budget
- Switch to Gemini paid tier (resolves non-commercial terms + training-data privacy on free tier); cost dashboard/alerts
- Migrate API from free host to always-warm host (~$7/mo) — cold starts are unacceptable for voice with real users
- Nightly Neo4j export to Supabase Storage + restore runbook (tested once)
- Error states everywhere voice can fail (no mic permission, STT unavailable, offline)
- Basic analytics (session count, retention, intent failure rate) and structured logging
- TestFlight + Play internal track builds; onboarding polish
- Pilot with 1–10 users; fix top issues

Exit criteria: pilot users complete ≥3 sessions each without developer intervention; LLM spend and quota headroom measured and acceptable.

### Phase 5 — MVP launch to ~100 users (week 10+)
- Open TestFlight/Play beta; monitoring + alerting on API errors, LLM failures, push delivery
- Weekly cost review; Aura Free headroom check (node counts vs. limit)
- Feedback loop → backlog for v2 (intent-based routing, hands-free/barge-in, richer analytics, skill templates)

---

## 3. Risks & mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Android STT quality varies by device/recognizer availability | Poor voice UX on some devices | Detect availability at runtime; fall back to chat; correction UX |
| Gemini free-tier requests-per-day exhausted during dev (limits change often — check current quotas in AI Studio) | Dev blocked mid-day | Flash-Lite for cheap calls; response caching; second dev project; upgrade early if friction |
| Free-tier data-use + non-commercial terms | Privacy/compliance at MVP | Paid tier switch is a Phase 4 gate, not optional |
| Aura Free auto-pauses on inactivity; no backups | Data loss / cold DB | Nightly export job (Phase 4); keep-alive ping during pilot; verify live node limits in console (docs conflict: 50K vs 200K) |
| LLM structured-output drift | Graph corruption | Pydantic validation + retries; intents (not Cypher) from LLM; audit log of applied intents |
| Voice latency (network + LLM) feels slow; free host cold starts add 30–60s after idle | Abandonment | Dev: tolerate cold starts or ping before demo sessions. Phase 4: warm host. Always: interim transcript shown instantly; short TTS acknowledgements while generating |
| Scope creep in wizard intelligence | Timeline slip | Wizard question set is fixed in v1 spec; free-form depth is v2 |

## 4. Running cost summary

| Item | Dev (1–10 users) | MVP (~100 users) |
|---|---|---|
| Gemini | $0 (free tier) | ~$5–15/mo (paid Flash) |
| Neo4j Aura | $0 | $0 |
| Supabase | $0 | $0 |
| API hosting | $0 (free tier, cold starts) | ~$7–10/mo (warm) |
| Expo push, STT/TTS | $0 | $0 |
| **Total** | **$0/mo** | **~$15–30/mo** |

## 5. Suggested spec-kit decomposition

One spec per phase-sized capability, in this order:
1. `foundations` — infra, auth, echo chat
2. `wizard-and-plan` — intents, schema, plan generation (largest spec; includes graph schema + intent vocabulary as constitution-level constraints)
3. `voice-layer`
4. `progress-and-notifications`
5. `hardening-and-pilot`

Constitution candidates (cross-cutting rules for spec-kit): LLM never writes Cypher; progress derived from CheckIns; single message pipeline with modality flag; all LLM outputs schema-validated; free→paid tier switch is config-only.

---

## 6. How this was built — spec-kit with Claude Code

> This section was the operating manual handed to Claude Code at the start: this document was the source of truth for architecture, schema, phasing, and constraints, and generated specs, plans, and tasks were not to contradict Sections 1–5. Where it was silent, decisions were recorded in the relevant spec. Kept as written (with command spelling updated) so the process is reproducible.

### 6.1 One-time setup

```bash
# Install the Specify CLI (spec-kit)
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git
specify version && specify check

# Initialize in the project root (note: v0.10+ uses --integration, the old --ai flag was removed)
specify init . --integration claude
```

Note: for Claude Code, spec-kit may install as **agent skills** (`.claude/skills/`) rather than slash-command files; invoked as `/speckit-*`. Run `specify integration list` if unsure.

### 6.2 Constitution (run once, before any feature spec)

Run `/speckit-constitution` with these non-negotiable principles (rephrase as needed, do not weaken):

1. **LLM never writes Cypher.** All LLM output is typed intents (JSON) validated against Pydantic schemas; a deterministic backend layer translates intents to parameterized Cypher. Validation failure → retry with error feedback (max 2), then graceful degradation to text-only reply.
2. **Progress is derived, never stored.** Progress/streaks/adherence are always computed from CheckIn nodes; no mutable progress counters anywhere.
3. **Goal history is immutable.** Goal revisions create new Goal nodes linked by SUPERSEDES; never overwrite.
4. **Single message pipeline.** Voice and chat produce identical message records distinguished only by a `modality` flag; nothing downstream may branch on modality.
5. **All LLM calls are budgeted.** Every call goes through a rate-limit queue with per-user daily budgets; Flash-Lite for cheap calls (summaries, classification), Flash for generation.
6. **Provider/tier switch is config-only.** Moving Gemini free→paid (or swapping models) must require zero code changes.
7. **Data placement rule.** Structured coaching state lives in Neo4j; transcripts, auth, push tokens, cadence schedules live in Supabase Postgres. Raw transcripts never enter the graph.
8. **Testing.** Intent→Cypher translation layer and context builder require unit tests; each spec's exit criteria become acceptance tests.
9. **Cost ceiling.** Dev runs at $0/mo (free tiers, cold starts accepted). Any deliverable that would introduce spend must be flagged, not silently added.

### 6.3 Feature specs — generate in this order

For each feature: `/speckit-specify` (what/why only — no tech stack) → `/speckit-clarify` → `/speckit-plan` (tech stack from Section 1 of this document) → `/speckit-tasks` → `/speckit-analyze` → `/speckit-implement`. Do not skip `/speckit-clarify` or `/speckit-analyze` for features 002 and 004 (highest ambiguity).

| # | Feature | /speckit-specify seed (what/why) | /speckit-plan seed (how) |
|---|---|---|---|
| 001 | `foundations` | Users can create an account, sign in on iOS/Android/web, and exchange a text message with an AI that responds. New signups are represented in the coaching graph. | Expo RN dev build; FastAPI on free host; Supabase auth + messages table; Neo4j Aura Free with (:User) on signup; LangChain→Gemini Flash-Lite echo; CI on both repos. Phase 0 exit criteria apply. |
| 002 | `wizard-and-plan` | A user picks a skill to learn; a wizard conversation elicits current level, target, timeline, weekly time; the system generates a structured learning plan the user can review. | Graph schema + intent vocabulary from Sections 1/6.2 verbatim. Pydantic schemas per intent; intent→Cypher layer with unit tests; context builder (profile + active-skill subgraph); Flash for plan generation. Phase 1 exit criteria apply. |
| 003 | `voice-layer` | Users can hold a button, speak, see/correct their transcript, and hear the coach's reply — full sessions hands-free-capable on iOS and Android; chat remains available everywhere. | expo-speech-recognition + expo-speech; push-to-talk with interim transcripts; interruptible TTS; permission denial states; Web Speech API on Chrome, chat fallback elsewhere; modality flag persisted. Phase 2 exit criteria apply. |
| 004 | `progress-and-notifications` | The coach checks on progress, celebrates it, helps diagnose obstacles, adapts goals, and proactively reminds users who fall behind their planned cadence; tapping a reminder resumes coaching with full awareness of the gap. | CheckIn/obstacle/goal-revision intents; Flash-Lite session summaries into Session nodes; last-N summaries in context; cadence table + pg_cron + pg_net + expo-notifications; deep links. Phase 3 exit criteria apply. |
| 005 | `hardening-and-pilot` | The product is reliable, private, recoverable, and observable enough for ~100 strangers. | Rate-limit queue + budgets; Gemini paid-tier config switch; warm-host migration (~$7/mo — first sanctioned spend); nightly Neo4j export + tested restore runbook; voice failure states; analytics; TestFlight/Play internal. Phase 4 exit criteria apply. |

### 6.4 Execution guardrails

- **Implement one feature at a time**, in numbered order; a feature's exit criteria (Section 2) must pass before starting the next.
- **Do not run `/speckit-implement` unattended on a full task list initially** — implement the first 3–5 tasks of feature 001, stop for human review, then proceed in larger batches.
- After each `/speckit-implement`, run `/speckit-converge` (if available in the installed version) to catch unbuilt tasks; repeat implement→converge until clean.
- **Ask the human** before: any spend, any schema change to Section 1's graph schema, any new third-party service, or deleting data.
- Verify live external limits rather than trusting this document's snapshots: Gemini quotas in AI Studio for the active project; Aura node limits in the Aura console.
- Keep secrets out of the repo; use `.env` locally and host-level secrets in deploys.

