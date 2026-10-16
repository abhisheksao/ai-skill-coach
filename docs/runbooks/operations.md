# Operations Runbook

Day-to-day operator procedures for the pilot (005, Hardening & Pilot).
Everything here runs from the Supabase SQL editor or a local `uv run`
command — no SSH, no separate ops UI (US4).

## Cost visibility (`ops_daily_spend`, `ops_user_daily_usage`)

Both are Postgres views over `llm_usage` (accumulated call counts +
token counts) x `model_rates` (seeded reference pricing). Query them in
the Supabase dashboard's SQL editor:

```sql
select * from ops_daily_spend order by day desc limit 7;
```

Example output:

| day | total_calls | total_prompt_tokens | total_output_tokens | estimated_usd |
|---|---|---|---|---|
| 2026-07-19 | 142 | 210500 | 48200 | 0.0303 |
| 2026-07-18 | 98 | 150200 | 33100 | 0.0212 |

```sql
select * from ops_user_daily_usage where day = current_date order by calls desc limit 20;
```

Per-user breakdown for the cost-spike edge case (spec Assumptions) and
FR-003's per-user visibility requirement.

**`model_rates` pricing is a placeholder seeded by the migration** —
verify the real per-1M-token price for the pinned model
(`gemini-3.1-flash-lite`, `render.yaml`'s `LLM_MODEL`) in the Google
Cloud console at (or before) the paid-tier switch, and keep it current:

```sql
update public.model_rates
set usd_per_1m_prompt_tokens = <verified value>,
    usd_per_1m_output_tokens = <verified value>,
    updated_at = now()
where model = 'gemini-3.1-flash-lite';
```

A price change is an `update`, not a deploy (research.md R7).

## Spend-threshold tuning

`.github/workflows/spend-check.yml` runs daily and fails (→ GitHub
failure email) when `ops_daily_spend`'s `estimated_usd` for today
exceeds `SPEND_ALERT_THRESHOLD_USD`. Tune the threshold by editing that
env value directly in the workflow file — no redeploy of the API needed.
To force a one-off test failure (proving the alert email actually
arrives): **Actions → Spend Check → Run workflow**, set
`threshold_override` to `0`. **Caveat found during T049 validation**:
the check is `spend > threshold` (strict), so `0` only forces a failure
if today's real spend is already nonzero — with genuinely zero spend
(e.g. no live token-accounting traffic yet), `$0.0000 > $0.00` is
`false` and the run succeeds. Use a **negative** override (e.g. `-1`)
to force a failure unconditionally, regardless of real spend.

## Alert-email validation log (T049)

Each of the 3 alert-carrying workflows deliberately failed once via
`workflow_dispatch` to prove GitHub's failure email actually reaches
the repo owner before being trusted for real incidents. None of these
touched real secrets — each uses an input override (`threshold_override`,
`neo4j_uri_override`, `health_url`) that falls back to the real
secret/default when omitted.

Record each forced run (date, workflow, override used, run link,
email received) in your own operations log.

## Paid-tier Gemini switch (config-only, Constitution VI)

Moving from the free-tier Gemini key to a billing-enabled paid-tier key
is a **secrets-only** change — `config.py` already isolates the API key
and model name behind `Settings`, so no code path branches on tier.

1. Create a new Google Cloud project with billing enabled (or use an
   existing billing-enabled project).
2. Mint a new Gemini API key under that project (Google AI Studio or
   Google Cloud Console, tied to the billing-enabled project — a key
   minted under a non-billing project stays free-tier regardless of
   where it's used).
3. On Render: **Environment** → set `GOOGLE_API_KEY` to the new paid key
   → save (triggers a redeploy).
4. **Same day**, remove the old free-tier (AI Studio) key from the
   Render environment entirely, so it can no longer serve pilot traffic
   even as a fallback (US2 scenario 1 — privacy terms only apply to
   paid-tier traffic).
5. Verify a live chat reply works against the new key.
6. **Zero-code-diff proof** (Constitution VI): `git diff` between the
   commit before and after this switch shows no source changes — only
   the Render dashboard's env var changed. Record the date here once
   done:

   | Date | Old key removed | Verified live | Zero-diff confirmed |
   |------|------------------|----------------|----------------------|
   | _(pending — human-executed, T031)_ | | | |

## Kill switch (per-user block)

`user_limits.blocked = true` makes a user's next chat turn behave
exactly like budget exhaustion (200, in-conversation
`errors.budget_exhausted_reply` turn, no automatic reset) — used for the
cost-spike edge case (a runaway client loop or abusive user).

```sql
-- Block:
insert into public.user_limits (user_id, blocked, note)
values ('<user-uuid>', true, 'runaway client loop 2026-08-02')
on conflict (user_id) do update set blocked = true, note = excluded.note, updated_at = now();

-- Unblock:
update public.user_limits set blocked = false, updated_at = now() where user_id = '<user-uuid>';

-- Or remove the row entirely (equivalent to unblocking, since absence means defaults):
delete from public.user_limits where user_id = '<user-uuid>';
```

## Per-user daily budget override

Same table, `daily_budget_override` — `null` uses the deployed
`DAILY_LLM_BUDGET` default; `0` pauses the user immediately (same
outward behavior as `blocked`, but framed as a budget of zero rather
than a hard block); any positive integer sets a custom daily cap.

```sql
insert into public.user_limits (user_id, daily_budget_override)
values ('<user-uuid>', 10)
on conflict (user_id) do update set daily_budget_override = excluded.daily_budget_override, updated_at = now();
```

## Logging policy (FR-007, research.md R14)

Every log line is a single JSON object (`logging_setup.py`'s
`JsonFormatter`). Two producers:

- **Request summary** (`RequestLogMiddleware`, every request):
  `request_id`, `method`, `path`, `status`, `duration_ms`, `sub`
  (pseudonymous, when authenticated).
- **`ai_failure`** (`log_ai_failure`, LLM failures at the chat seam):
  `endpoint`, `sub`, `intent_type` (`wizard`/`coaching`), `failure_class`
  (e.g. `LlmUnavailable`, `validation_exhausted`).

**Never logged, anywhere, by design** — not a manual discipline, a
structural guarantee: `JsonFormatter` only ever merges a small,
pre-built dict from a named extra attribute (`request_log` or
`ai_failure`) into the output; there is no code path that logs a raw
exception's message, a request/response body, a chat message, or a
secret (API keys, JWTs, service-role keys). Proven by
`test_log_redaction.py`, which drives a real chat turn carrying a
sentinel string and its own JWT through the whole pipeline and asserts
neither ever appears in any captured log record.

## Render log search

Render's dashboard **Logs** tab is plain full-text search over these
JSON lines — no separate log aggregation service needed at pilot scale.
Useful searches:

- `"ai_failure"` — every LLM failure, with `intent_type`/`failure_class`
  to triage without needing the user's transcript.
- `"request_id":"<id>"` — every log line for one specific request (the
  id is also returned in the response's `x-request-id` header, so a
  client-reported issue can be traced directly).
- `"status":5` — 5xx responses across the fleet.

## SC-005 query cookbook

All four `ops_*` analytics views answer SC-005 ("operator can see
sessions/retention/failures within minutes, dashboards alone"):

```sql
-- Sessions started/ended per day
select * from ops_daily_sessions order by day desc limit 14;

-- Day-over-day retention (returning vs. new active users)
select * from ops_retention order by day desc limit 14;

-- Intent-validation failure rate (validation_failures / session_started-proxied turns)
select * from ops_intent_failure_rate order by day desc limit 14;

-- Push delivery outcomes
select * from ops_push_outcomes order by day desc limit 14;

-- Pilot exit bar (>= 3 completed sessions per pilot user, SC-001)
select * from ops_pilot_exit_bar order by completed_sessions desc;
```

## Weekly external-limits review (research.md R15)

Verify these live in each provider's console — never trust a number
from a planning document or a prior week's row below. Log the date and
findings here every week during the pilot:

| Date | Gemini paid quota (RPM/RPD) | Aura node/rel count vs. ceiling | Supabase storage/DB size | Render plan status |
|------|------------------------------|-----------------------------------|---------------------------|----------------------|
| _(pending — first review after pilot start)_ | | | | |

- **Gemini**: Google Cloud Console → APIs & Services → the pinned
  model's quota page (paid-tier numbers, not the free-tier ones from
  001).
- **Aura**: the console's own node/relationship counts for your
  instance against its free-tier ceiling (docs disagree on the exact
  number — read the console's own reported limit).
- **Supabase**: Project Settings → Usage — storage (includes
  `graph-exports`), database size, and confirm `pg_cron`/`pg_net` are
  still enabled.
- **Render**: confirm the Starter plan is still active (always-on, no
  idle spin-down).
