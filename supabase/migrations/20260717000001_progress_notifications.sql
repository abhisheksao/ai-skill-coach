-- 004 Progress Loop & Notifications: cadence_schedules, push_tokens,
-- notifications (specs/004-progress-and-notifications/data-model.md).
-- Applied automatically by the Supabase GitHub integration on push to main.
-- Service-role-only writes, same posture as messages/llm_usage -- clients
-- never write these directly.

-- --------------------------------------------------------- cadence_schedules
-- Relational projection of each active step's expected rhythm (research R8),
-- synced whenever a create_plan/revise_plan intent applies.
create table if not exists public.cadence_schedules (
    user_id           uuid not null,
    skill_id          text not null,
    step_order        integer not null,
    cadence_per_week  integer not null,
    updated_at        timestamptz not null default now(),
    primary key (user_id, skill_id, step_order)
);

alter table public.cadence_schedules enable row level security;
-- No policies at all: service-role only, same as llm_usage.

-- --------------------------------------------------------------- push_tokens
-- Managed lifecycle per FR-013 -- multiple rows per user (one per device).
create table if not exists public.push_tokens (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references auth.users (id) on delete cascade,
    token      text not null,
    platform   text not null check (platform in ('ios', 'android', 'web')),
    created_at timestamptz not null default now(),
    revoked_at timestamptz
);
create unique index if not exists push_tokens_user_token_idx
    on public.push_tokens (user_id, token) where revoked_at is null;

alter table public.push_tokens enable row level security;
-- No policies: service-role only.

-- ----------------------------------------------------------------- notifications
-- Delivery log; also the source of truth for the frequency cap
-- (constants.NOTIFICATION_MAX_PER_SKILL_PER_DAY / _PER_WEEK).
create table if not exists public.notifications (
    id               uuid primary key default gen_random_uuid(),
    user_id          uuid not null references auth.users (id) on delete cascade,
    skill_id         text not null,
    sent_at          timestamptz not null default now(),
    gap_description  text not null,
    delivery_status  text not null check (
        delivery_status in ('sent', 'failed', 'skipped_no_token', 'skipped_permission_denied')
    ),
    created_at       timestamptz not null default now()
);
create index if not exists notifications_user_sent_idx
    on public.notifications (user_id, sent_at);

alter table public.notifications enable row level security;
-- No policies: service-role only.

-- ---------------------------------------------------- session summarization
-- PostgREST has no GROUP BY/HAVING; the session-summarize job (research R2)
-- needs "every (user, skill, session) whose last message is older than a
-- cutoff, with no Session node in Neo4j yet" -- the Neo4j half can't be
-- expressed in SQL at all, so this RPC only does the Postgres-side fan-out
-- (candidates), same division of labor as the notifications scan (R1).
create or replace function public.eligible_sessions_for_summary(cutoff timestamptz)
returns table (user_id uuid, skill_id uuid, session_id uuid, started_at timestamptz, ended_at timestamptz)
language sql
security definer
set search_path = public
as $$
    select user_id, skill_id, session_id, min(created_at) as started_at, max(created_at) as ended_at
    from public.messages
    where skill_id is not null
    group by user_id, skill_id, session_id
    having max(created_at) < cutoff
$$;

revoke execute on function public.eligible_sessions_for_summary(timestamptz) from public, anon, authenticated;
