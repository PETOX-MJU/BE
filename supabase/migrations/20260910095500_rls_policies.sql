-- 개인 데이터는 user_id 컬럼 + RLS로 격리한다. user_id 없는 테이블(detected_apps, items)은
-- 전원 공유 카탈로그라 읽기만 열어둔다. coin_ledger·user_items는 쓰기 정책을 안 둔다 —
-- RPC(security definer)만 쓸 수 있게 해서 신뢰 로직을 우회할 수 없게 한다(ADR-004).
-- missions는 user_id가 없지만(일별로 개인화 생성됨, ADR-005) user_missions를 거쳐 내 것만 보이게 한다.

-- profiles
alter table profiles enable row level security;
create policy "own profile select" on profiles for select using (id = auth.uid());
create policy "own profile update" on profiles for update using (id = auth.uid());
create policy "own profile insert" on profiles for insert with check (id = auth.uid());

-- pets
alter table pets enable row level security;
create policy "own pets" on pets for select using (user_id = auth.uid());
create policy "own pets insert" on pets for insert with check (user_id = auth.uid());
create policy "own pets update" on pets for update using (user_id = auth.uid());
create policy "own pets delete" on pets for delete using (user_id = auth.uid());

-- user_detected_apps
alter table user_detected_apps enable row level security;
create policy "own detected app settings" on user_detected_apps for select using (user_id = auth.uid());
create policy "own detected app settings insert" on user_detected_apps for insert with check (user_id = auth.uid());
create policy "own detected app settings update" on user_detected_apps for update using (user_id = auth.uid());

-- daily_usage — 클라가 직접 upsert(ADR-003)
alter table daily_usage enable row level security;
create policy "own daily usage" on daily_usage for select using (user_id = auth.uid());
create policy "own daily usage insert" on daily_usage for insert with check (user_id = auth.uid());
create policy "own daily usage update" on daily_usage for update using (user_id = auth.uid());

-- user_missions — 읽기만. 상태 변경은 complete_mission RPC로만(ADR-004).
alter table user_missions enable row level security;
create policy "own user_missions select" on user_missions for select using (user_id = auth.uid());

-- missions — user_id가 없어서 user_missions를 거쳐 내 것만 노출
alter table missions enable row level security;
create policy "missions via my user_missions" on missions for select
  using (exists (
    select 1 from user_missions um
    where um.mission_id = missions.id and um.user_id = auth.uid()
  ));

-- coin_ledger — 읽기만. 쓰기는 RPC로만(ADR-004).
alter table coin_ledger enable row level security;
create policy "own coin_ledger select" on coin_ledger for select using (user_id = auth.uid());

-- user_items — 읽기만. 구매는 buy_item RPC로만(ADR-004).
alter table user_items enable row level security;
create policy "own user_items select" on user_items for select using (user_id = auth.uid());
create policy "own user_items update" on user_items for update using (user_id = auth.uid()); -- 장착/해제용

-- notification_settings
alter table notification_settings enable row level security;
create policy "own notification settings" on notification_settings for select using (user_id = auth.uid());
create policy "own notification settings insert" on notification_settings for insert with check (user_id = auth.uid());
create policy "own notification settings update" on notification_settings for update using (user_id = auth.uid());

-- 공유 카탈로그 — 로그인한 사용자는 읽기만
alter table detected_apps enable row level security;
create policy "detected_apps readable" on detected_apps for select using (auth.role() = 'authenticated');

alter table items enable row level security;
create policy "items readable" on items for select using (auth.role() = 'authenticated');
