-- 005 Hardening & Pilot: analytics_events, user_limits, model_rates,
-- llm_usage token accounting + record_llm_tokens RPC, ops_* operator views,
-- the private graph-exports storage bucket
-- (specs/005-hardening-and-pilot/data-model.md).
-- Applied automatically by the Supabase GitHub integration on push to main.
-- Service-role-only writes, same posture as llm_usage/push_tokens.

-- ---------------------------------------------------------- llm_usage (extend)
-- Token accounting so spend is estimable per user-day (research.md R7).
-- increment_llm_usage(uid) keeps its existing call-counting contract
-- unchanged (the pre-call budget gate) -- only the table gains columns.
alter table public.llm_usage
    add column if not exists prompt_tokens bigint not null default 0,
    add column if not exists output_tokens bigint not null default 0;

-- Post-call actuals recorder -- separate from increment_llm_usage because
-- tokens are only known after the call returns, while the call count must
-- be reserved before it.
create or replace function public.record_llm_tokens(uid uuid, p_prompt bigint, p_output bigint)
returns void
language sql
security definer
set search_path = public
as $$
    insert into public.llm_usage (user_id, usage_date, count, prompt_tokens, output_tokens)
    values (uid, current_date, 0, p_prompt, p_output)
    on conflict (user_id, usage_date)
    do update set
        prompt_tokens = public.llm_usage.prompt_tokens + excluded.prompt_tokens,
        output_tokens = public.llm_usage.output_tokens + excluded.output_tokens;
$$;

revoke execute on function public.record_llm_tokens(uuid, bigint, bigint) from public, anon, authenticated;

-- --------------------------------------------------------------- user_limits
-- Per-user override / kill switch, consulted by BudgetGuard.acquire (R1).
-- Rows exist only for exceptions -- absence means defaults apply.
create table if not exists public.user_limits (
    user_id               uuid primary key references auth.users (id) on delete cascade,
    daily_budget_override integer check (daily_budget_override >= 0),
    blocked               boolean not null default false,
    note                  text,
    updated_at            timestamptz not null default now()
);

alter table public.user_limits enable row level security;
-- No policies: service-role only, same posture as llm_usage.

-- --------------------------------------------------------------- model_rates
-- Reference data for spend estimation (R7); a price change is an UPDATE,
-- not a deploy. Seed row is for the currently pinned model (render.yaml's
-- LLM_MODEL) -- rates are placeholder figures and MUST be verified against
-- the live Google Cloud pricing console before/at the paid-tier switch
-- (T031, research.md R15's live-verification rule) and updated here.
create table if not exists public.model_rates (
    model                    text primary key,
    usd_per_1m_prompt_tokens numeric not null,
    usd_per_1m_output_tokens numeric not null,
    updated_at               timestamptz not null default now()
);

alter table public.model_rates enable row level security;
-- No policies: service-role only.

insert into public.model_rates (model, usd_per_1m_prompt_tokens, usd_per_1m_output_tokens)
values ('gemini-3.1-flash-lite', 0.075, 0.30)
on conflict (model) do nothing;

-- ----------------------------------------------------------- analytics_events
-- Server-side writes only (R8). Pseudonymous; `properties` MUST never
-- contain message/transcript bodies or secrets (FR-007; redaction-tested).
create table if not exists public.analytics_events (
    id          bigint generated always as identity primary key,
    occurred_at timestamptz not null default now(),
    user_sub    uuid,
    event_type  text not null check (event_type in (
        'session_started', 'session_ended', 'intent_validation_failed',
        'push_sent', 'push_failed'
    )),
    properties  jsonb not null default '{}'::jsonb
);

create index if not exists analytics_events_occurred_at_idx
    on public.analytics_events (occurred_at);
create index if not exists analytics_events_type_occurred_at_idx
    on public.analytics_events (event_type, occurred_at);

alter table public.analytics_events enable row level security;
-- No policies: server-side writes only, same posture as llm_usage.

-- ------------------------------------------------------------------ ops_* views
-- Read in the Supabase SQL editor (US4: no SSH); documented with example
-- output in docs/runbooks/operations.md. Views execute with the OWNER's
-- table-visibility by default in Postgres (not the querying role's) --
-- explicit revokes below stop these from becoming an accidental read-any-
-- user's-data hole for the anon/authenticated client roles, matching the
-- revoke posture already used on every service-role-only RPC in this repo.

create or replace view public.ops_daily_spend as
select
    usage_date as day,
    sum(count) as total_calls,
    sum(prompt_tokens) as total_prompt_tokens,
    sum(output_tokens) as total_output_tokens,
    round(
        (sum(prompt_tokens)::numeric / 1000000)
            * (select usd_per_1m_prompt_tokens from public.model_rates order by updated_at desc limit 1)
        + (sum(output_tokens)::numeric / 1000000)
            * (select usd_per_1m_output_tokens from public.model_rates order by updated_at desc limit 1),
        4
    ) as estimated_usd
from public.llm_usage
group by usage_date
order by usage_date desc;

create or replace view public.ops_user_daily_usage as
select user_id, usage_date as day, count as calls, prompt_tokens, output_tokens
from public.llm_usage
order by usage_date desc, user_id;

create or replace view public.ops_daily_sessions as
select
    occurred_at::date as day,
    count(*) filter (where event_type = 'session_started') as sessions_started,
    count(*) filter (where event_type = 'session_ended') as sessions_ended
from public.analytics_events
where event_type in ('session_started', 'session_ended')
group by occurred_at::date
order by day desc;

create or replace view public.ops_retention as
with daily_active as (
    select distinct occurred_at::date as day, user_sub
    from public.analytics_events
    where event_type = 'session_started' and user_sub is not null
)
select
    d.day,
    count(distinct d.user_sub) as active_users,
    count(distinct d.user_sub) filter (
        where exists (
            select 1 from daily_active earlier
            where earlier.user_sub = d.user_sub and earlier.day < d.day
        )
    ) as returning_users
from daily_active d
group by d.day
order by d.day desc;

create or replace view public.ops_intent_failure_rate as
select
    occurred_at::date as day,
    count(*) filter (where event_type = 'intent_validation_failed') as validation_failures,
    count(*) filter (where event_type = 'session_started') as turns_proxy,
    round(
        count(*) filter (where event_type = 'intent_validation_failed')::numeric
        / nullif(count(*) filter (where event_type = 'session_started'), 0),
        4
    ) as failure_rate
from public.analytics_events
where event_type in ('intent_validation_failed', 'session_started')
group by occurred_at::date
order by day desc;

create or replace view public.ops_push_outcomes as
select
    occurred_at::date as day,
    count(*) filter (where event_type = 'push_sent') as sent,
    count(*) filter (where event_type = 'push_failed') as failed
from public.analytics_events
where event_type in ('push_sent', 'push_failed')
group by occurred_at::date
order by day desc;

create or replace view public.ops_pilot_exit_bar as
select
    user_sub as user_id,
    count(*) filter (where event_type = 'session_ended') as completed_sessions,
    count(*) filter (where event_type = 'session_ended') >= 3 as meets_exit_bar
from public.analytics_events
where user_sub is not null
group by user_sub
order by completed_sessions desc;

revoke select on
    public.ops_daily_spend,
    public.ops_user_daily_usage,
    public.ops_daily_sessions,
    public.ops_retention,
    public.ops_intent_failure_rate,
    public.ops_push_outcomes,
    public.ops_pilot_exit_bar
from public, anon, authenticated;

-- ------------------------------------------------------- graph-exports bucket
-- Private (public=false); service-role access only, matching the spec's
-- backup-access-control edge case. No storage.objects policies needed --
-- only the service-role key (export/restore scripts) ever touches it.
insert into storage.buckets (id, name, public)
values ('graph-exports', 'graph-exports', false)
on conflict (id) do nothing;
