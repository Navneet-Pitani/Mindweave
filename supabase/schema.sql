-- Run once in your project's Supabase SQL Editor. Non-destructive, app-specific names.
begin;
create table if not exists public.mw_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text not null default '' check (char_length(display_name) <= 80),
  preferences jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create table if not exists public.mw_conversations (
  id uuid primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(title) <= 80),
  created_at timestamptz not null default now(),
  unique (id, user_id)
);
create table if not exists public.mw_turns (
  id uuid primary key,
  conversation_id uuid not null,
  user_id uuid not null references auth.users(id) on delete cascade,
  user_message text not null check (char_length(user_message) <= 4000),
  assistant_response text not null,
  result jsonb not null default '{}'::jsonb,
  feedback text check (feedback in ('helped','a_little','not_helped')),
  created_at timestamptz not null default now(),
  foreign key (conversation_id, user_id) references public.mw_conversations(id, user_id) on delete cascade
);
create index if not exists mw_conversations_owner on public.mw_conversations(user_id, created_at desc);
create index if not exists mw_turns_conversation on public.mw_turns(conversation_id, created_at);
alter table public.mw_profiles enable row level security;
alter table public.mw_conversations enable row level security;
alter table public.mw_turns enable row level security;
revoke all on public.mw_profiles, public.mw_conversations, public.mw_turns from anon;
grant select, insert, update, delete on public.mw_profiles, public.mw_conversations, public.mw_turns to authenticated;
do $$
declare t text;
begin
  foreach t in array array['mw_profiles','mw_conversations','mw_turns'] loop
    if not exists (select 1 from pg_policies where schemaname='public' and tablename=t and policyname='owner_only') then
      execute format('create policy owner_only on public.%I for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id)', t);
    end if;
  end loop;
end $$;
commit;
