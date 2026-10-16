-- 003 Voice Layer: persisted spoken-replies preference (FR-004).
-- Additive, backward-compatible -- existing rows default to true so no
-- backfill is needed.
alter table public.profiles
    add column voice_replies_enabled boolean not null default true;
