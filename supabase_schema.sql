-- LQ DRAFT INTEL — Supabase schema
-- Jalankan seluruh file ini di Supabase Dashboard → SQL Editor → New query → Run

create table if not exists drafts (
  id                bigint generated always as identity primary key,
  week              text,
  day               text,
  game              text,
  date              text,
  team_a            text not null,
  team_b            text not null,
  blue_picks        text[] default '{}',
  red_picks         text[] default '{}',
  blue_bans         text[] default '{}',
  red_bans          text[] default '{}',
  winner            text,
  time              text,
  result_a          text,
  result_b          text,
  blue_draft_order  text[] default '{}',
  red_draft_order   text[] default '{}',
  blue_ban_order    text[] default '{}',
  red_ban_order     text[] default '{}',
  blue_pick_roles   text[] default '{}',
  red_pick_roles    text[] default '{}',
  created_at        timestamptz not null default now()
);

create table if not exists matches_master (
  id                bigint generated always as identity primary key,
  date              text,
  date_iso          text,
  week              text,
  day               text,
  game              text,
  team_a            text,
  team_b            text,
  winner            text,
  score_a           text,
  score_b           text,
  blue_picks        text,
  red_picks         text,
  blue_bans         text,
  red_bans          text,
  result_a          text,
  result_b          text,
  time              text,
  blue_draft_order  text,
  red_draft_order   text,
  source_file       text
);

-- RLS: kunci akses publik, hanya service_role (dipakai backend) yang bisa baca/tulis.
alter table drafts enable row level security;
alter table matches_master enable row level security;
-- Tidak ada policy dibuat secara sengaja: service_role selalu bypass RLS,
-- sedangkan anon/publik akan ditolak total karena tidak ada policy yang mengizinkan.
