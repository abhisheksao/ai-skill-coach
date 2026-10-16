-- 001 Foundations: profiles, messages, llm_usage (specs/001-foundations/data-model.md)
-- Applied automatically by the Supabase GitHub integration on push to main,
-- or manually via: supabase db push (after supabase link)
-- Clients get read-only access to their own rows; ALL writes go through the API
-- service role (Constitution I/IV; research R9).

-- ---------------------------------------------------------------- profiles
create table if not exists public.profiles (
    user_id      uuid primary key references auth.users (id) on delete cascade,
    display_name text,
    language     text not null check (language in ('en', 'hi', 'es', 'fr', 'de')),
    timezone     text not null,
    consent_at   timestamptz not null,
    created_at   timestamptz not null default now(),
    updated_at   timestamptz not null default now()
);

alter table public.profiles enable row level security;

drop policy if exists profiles_select_own on public.profiles;
create policy profiles_select_own on public.profiles
    for select using (user_id = auth.uid());

-- No insert/update/delete policies: only the service role (bypasses RLS) writes.

-- ---------------------------------------------------------------- messages
create table if not exists public.messages (
    id         uuid primary key default gen_random_uuid(),
    user_id    uuid not null references auth.users (id) on delete cascade,
    session_id uuid not null,
    skill_id   uuid,
    sender     text not null check (sender in ('user', 'assistant')),
    content    text not null,
    modality   text not null default 'chat' check (modality in ('chat', 'voice')),
    created_at timestamptz not null default now()
);

create index if not exists messages_user_session_created_idx
    on public.messages (user_id, session_id, created_at);

alter table public.messages enable row level security;

drop policy if exists messages_select_own on public.messages;
create policy messages_select_own on public.messages
    for select using (user_id = auth.uid());

-- No write policies: the API service role is the single writer (single pipeline).

-- ---------------------------------------------------------------- llm_usage
create table if not exists public.llm_usage (
    user_id    uuid not null,
    usage_date date not null default current_date,
    count      integer not null default 0,
    primary key (user_id, usage_date)
);

alter table public.llm_usage enable row level security;
-- No policies at all: service-role only.

-- Atomic per-user daily counter for the v0 budget guard (research R6).
create or replace function public.increment_llm_usage(uid uuid)
returns integer
language sql
security definer
set search_path = public
as $$
    insert into public.llm_usage (user_id, usage_date, count)
    values (uid, current_date, 1)
    on conflict (user_id, usage_date)
    do update set count = llm_usage.count + 1
    returning count;
$$;

revoke execute on function public.increment_llm_usage(uuid) from public, anon, authenticated;
