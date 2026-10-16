# Quickstart Validation: Hardening & Pilot (005)

**Date**: 2026-07-18 | **Spec**: [spec.md](spec.md) | **Contracts**: [contracts/api.md](contracts/api.md)

Runnable proof for each user story. Automated suites are the source of
truth (Constitution VIII); the live checks below exist because 005's
subject matter — real spend, real stores, real devices, real backups —
partly lives outside any test harness. Every manual pass here must have a
row in `docs/testing.md`'s checklist at the exit gate.

## Prerequisites

- `api/`: `uv sync --frozen`; `app/`: `npm install`.
- Human-executed items from `docs/getting-started.md` (Constitution IX —
  never performed by a task): Render Starter upgrade, paid-tier Gemini
  key, Apple Developer Program, Play Console, GH repo secrets for the
  workflows (`NEO4J_*`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`).

## Automated suites

```bash
cd api && uv run pytest -m hardening      # queue, budget turn, analytics,
                                          # export/restore round-trip,
                                          # spend check, log redaction
cd app && npm test                        # voice failure reducers, offline
                                          # queue, onboarding gating
cd app && npx playwright test             # budget turn in-conversation,
                                          # offline compose→reconnect,
                                          # onboarding, delete-account entry
```

## US1 — Heavy use never breaks the product or the budget (P1)

1. **Queue under provider pressure** (automated + scripted load): run
   the load script against a local API wired to a fake runnable that
   429s the first N attempts —
   `uv run python scripts/load_sim.py --users 10 --burst 5` (built in
   this feature). Expect: all requests end in a coach reply or the
   degraded/unavailable i18n keys; **zero** raw provider errors in
   responses; request log shows queue waits, not failures.
2. **Budget exhaustion is friendly**: set `DAILY_LLM_BUDGET=2` locally,
   send 3 messages. Third response is 200 with
   `errors.budget_exhausted_reply` + `resets_at`; UI shows it as a
   normal coach bubble (Playwright-covered). Other user unaffected
   (second test user still gets replies).
3. **Cost view**: after the above, open Supabase SQL editor →
   `select * from ops_daily_spend; select * from ops_user_daily_usage;`
   — today's calls/tokens/estimated USD appear.
4. **Spend alert fires**: run the spend-check workflow manually
   (`workflow_dispatch`) with threshold `0` → workflow fails → GitHub
   failure email arrives. Restore the real threshold.
5. **Kill switch**: insert a `user_limits` row with `blocked=true` for a
   test user → their next message gets the exhausted-style turn; delete
   the row → replies resume.

## US2 — Private and recoverable (P1)

1. **Config-only tier switch**: swap `GOOGLE_API_KEY` to the paid-tier
   key on Render, remove the free key, redeploy. Verify a live reply,
   then `git diff` shows **zero code change** (Constitution VI proof).
2. **Nightly export exists**: after one scheduled run (or
   `workflow_dispatch`), confirm `graph-export-<today>.json` in the
   private `graph-exports` bucket; download and eyeball `counts`.
3. **Missed export alerts**: run the export workflow once with a
   deliberately broken secret → failure email arrives.
4. **Restore rehearsal (SC-003, before first invite)**: follow
   `docs/runbooks/restore.md` against a scratch/empty Aura instance:
   `uv run python scripts/restore_graph.py --file graph-export-<date>.json --uri <scratch-uri> ...`
   — script reports node/relationship counts matching the artifact's
   independent `counts`; spot-check one user's skills/plans/check-ins
   by query. Record the rehearsal date in the runbook.

## US3 — Voice failure states are honest (P2)

Walk the R9 matrix; web cells are Playwright-automated, device cells are
manual/Maestro rows in `docs/testing.md`:

| Cell | How to drive | Expect |
|------|--------------|--------|
| V1 deny mic | fresh install, deny | existing guidance state, chat works |
| V2 revoke mid-session | OS settings mid-session, return, press mic | specific guidance, same conversation continues by chat |
| V3 no recognizer | emulator without speech engine / unsupported browser | unavailable state, chat works |
| V4 offline send | airplane mode, type, send | input preserved, marked failed with retry; reconnect → sends |
| V5 offline mid-speech | airplane mode while dictating | interim transcript lands in composer, connection-lost state |
| V6 TTS unavailable | disable TTS engine (Android) | reply shown as text + banner; no crash |
| V7 audio focus lost | incoming call while dictating | clean stop, partial preserved, resume state |

Every cell: text composer enabled, state names the problem and remedy.

## US4 — Operator can see what's happening (P2)

1. Generate known traffic: one full session, one forced validation
   failure (fake-runnable local run), one push (existing 004 flow).
2. Supabase SQL editor: `ops_daily_sessions`, `ops_retention`,
   `ops_intent_failure_rate`, `ops_push_outcomes` each show today's
   event (SC-005: minutes, dashboards alone).
3. Render logs: search the request id from step 1's failure — the
   `ai_failure` entry carries endpoint, pseudonymous sub, intent type;
   grep the log stream for a sentinel phrase you typed in chat →
   **zero hits** (FR-007; also pytest-enforced).
4. Healthcheck alert: point `healthcheck.yml` at an invalid URL via
   `workflow_dispatch` input (or temporarily suspend the service) →
   failure email arrives.

## US5 — Strangers can install and start unaided (P1)

1. **Latency precondition (R10)**: with the warm host live, run 20
   scripted chat turns across an hour;
   `duration_ms` p90 on `POST /v1/chat` < 3000 (query documented in
   `docs/runbooks/operations.md`).
2. **Release runbook executed**: follow `docs/runbooks/release.md` once
   per platform — TestFlight build visible to an internal tester;
   Play internal track install link works.
3. **Unaided install test**: send the invite to one fresh device owned
   by someone new. Observe without helping: install → onboarding
   explainer (push-to-talk + notifications, contextual permission asks)
   → first session completed. Sign in with Apple visible on iOS.
4. **Deletion entry**: Settings → Delete account opens the configured
   URL; `docs/runbooks/deletion.md` executed once against a test
   account (graph subgraph gone, auth user gone, verified by query).
5. **Live limits verified (FR-011/R15)**: record in this file's exit
   notes — paid Gemini quotas, Aura node ceiling + current counts,
   Supabase storage/DB headroom, Render always-on confirmed.

## Exit gate

- All automated suites green; `docs/testing.md` updated with 005's
  section (automated index + manual matrix).
- SC-001–SC-005 each checked against its scenario above during the
  pilot window; alert emails proven (each workflow failed once on
  purpose).
- `docs/getting-started.md` spend rows marked executed with dates.
