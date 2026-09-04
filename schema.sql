-- PETOX DB 스키마 (Supabase)
-- Supabase 대시보드 > SQL Editor 에 그대로 붙여넣어 실행하면 됨.

create table profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  goal_minutes int not null default 60,
  focus_start time,
  focus_end time,
  bedtime time,
  created_at timestamptz not null default now()
);

create table pets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  source_photo_url text,
  pixel_image_url text,
  is_default boolean not null default false,
  level int not null default 1,
  affection int not null default 0,
  created_at timestamptz not null default now()
);

create table detected_apps (
  id uuid primary key default gen_random_uuid(),
  package_name text not null unique,
  display_name text not null
);

insert into detected_apps (package_name, display_name) values
  ('com.zhiliaoapp.musically', '틱톡'),
  ('com.instagram.android', '인스타그램 릴스'),
  ('com.google.android.youtube', '유튜브 쇼츠');

create table user_detected_apps (
  user_id uuid not null references auth.users(id) on delete cascade,
  app_id uuid not null references detected_apps(id) on delete cascade,
  is_enabled boolean not null default true,
  primary key (user_id, app_id)
);

create table usage_logs (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  app_id uuid not null references detected_apps(id),
  started_at timestamptz not null,
  ended_at timestamptz,
  duration_seconds int
);

create table missions (
  id uuid primary key default gen_random_uuid(),
  type text not null check (type in ('daily', 'weekly')),
  title text not null,
  target_minutes int not null,
  reward_coins int not null default 0,
  valid_date date not null
);

create table user_missions (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  mission_id uuid not null references missions(id) on delete cascade,
  status text not null default 'in_progress' check (status in ('in_progress', 'completed', 'failed')),
  coins_earned int not null default 0,
  completed_at timestamptz,
  unique (user_id, mission_id)
);

create table coin_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  amount int not null,
  reason text not null,
  created_at timestamptz not null default now()
);

create table items (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null check (type in ('clothing', 'pet_slot')),
  price_coins int not null,
  image_url text
);

create table user_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  item_id uuid not null references items(id) on delete cascade,
  purchased_at timestamptz not null default now(),
  is_equipped boolean not null default false
);

create table notification_settings (
  user_id uuid primary key references auth.users(id) on delete cascade,
  mission_alert boolean not null default true,
  report_alert boolean not null default true
);

-- FK 컬럼 인덱스
create index idx_pets_user_id on pets(user_id);
create index idx_user_detected_apps_app_id on user_detected_apps(app_id);
create index idx_usage_logs_user_id on usage_logs(user_id);
create index idx_usage_logs_app_id on usage_logs(app_id);
create index idx_user_missions_user_id on user_missions(user_id);
create index idx_user_missions_mission_id on user_missions(mission_id);
create index idx_coin_ledger_user_id on coin_ledger(user_id);
create index idx_user_items_user_id on user_items(user_id);
create index idx_user_items_item_id on user_items(item_id);
