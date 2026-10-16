-- Explicit Data API grants.
--
-- Older Supabase projects auto-granted every privilege on new public
-- tables to anon/authenticated/service_role (default privileges), with Row
-- Level Security doing the real gating. Newer projects and the local CLI
-- stack no longer do: a fresh database gets the tables but the API roles
-- can't read them ("permission denied for table profiles"). Found by the
-- fresh-database test of the open-source export (2026-10-13).
--
-- Grant exactly what the code uses, so behaviour doesn't depend on the
-- project's age. On projects that already have the broad defaults this is
-- a no-op: nothing here revokes.

-- The API talks to Postgres only as service_role (PostgREST + RPCs).
grant usage on schema public to service_role;
grant select, insert, update, delete on all tables in schema public to service_role;
grant usage, select on all sequences in schema public to service_role;
grant execute on function public.increment_llm_usage(uuid) to service_role;
grant execute on function public.record_llm_tokens(uuid, bigint, bigint) to service_role;
grant execute on function public.eligible_sessions_for_summary(timestamptz) to service_role;

-- The app reads its own profile and chat history directly (supabase-js,
-- signed-in user). RLS policies profiles_select_own / messages_select_own
-- limit this to the caller's rows; there are no client write paths.
grant usage on schema public to authenticated;
grant select on public.profiles, public.messages to authenticated;
