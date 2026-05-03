-- Run this in your Supabase SQL Editor
-- Dashboard → SQL Editor → New query → paste → Run

create table if not exists waitlist (
  id           uuid        default gen_random_uuid() primary key,
  created_at   timestamptz default now() not null,
  name         text,
  email        text        not null,
  role         text,
  framework    text,
  pain_point   text,
  would_pay    text,
  constraint waitlist_email_unique unique (email)
);

-- Enable Row Level Security
alter table waitlist enable row level security;

-- Allow inserts from the API (server-side uses secret key which bypasses RLS)
-- This policy is a safety net for the publishable key if ever used client-side
create policy "allow_insert" on waitlist
  for insert with check (true);
