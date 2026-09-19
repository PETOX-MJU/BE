-- ADR-25/26: 대시보드의 오늘의 미션 3장(앱별 2개 + 펫 호출 횟수)과 수령·자동 정산.
--
-- 미션의 "날짜"는 KST다. 사용시간(daily_usage.usage_date)이 기기 날짜(KST)로 쌓이므로
-- 판정 기준일이 같아야 한다. cron도 KST 06:00(UTC 21:00)으로 옮긴다.

-- 펫 호출 횟수: 클라이언트가 직접 쓴다(daily_usage와 같은 신뢰 수준, ADR-003).
create table daily_pet_calls (
  user_id uuid not null references auth.users(id) on delete cascade,
  usage_date date not null,
  calls int not null default 0 check (calls >= 0),
  primary key (user_id, usage_date)
);

alter table daily_pet_calls enable row level security;
create policy "own pet calls" on daily_pet_calls for select using (user_id = auth.uid());
create policy "own pet calls insert" on daily_pet_calls for insert with check (user_id = auth.uid());
create policy "own pet calls update" on daily_pet_calls for update using (user_id = auth.uid());

-- 미션 모델: app_id가 없으면 전체 앱 합산. target은 metric에 따라 분(target_minutes) 또는
-- 횟수(target_count) 중 하나만 채운다.
alter table missions
  alter column target_minutes drop not null,
  add column app_id uuid references detected_apps(id),
  add column metric text not null default 'usage_minutes'
    check (metric in ('usage_minutes', 'pet_calls')),
  add column target_count int;

alter table missions add constraint missions_metric_target check (
  (metric = 'usage_minutes' and target_minutes is not null and target_count is null)
  or (metric = 'pet_calls' and target_count is not null and target_minutes is null
      and app_id is null)
);

create index idx_missions_app_id on missions(app_id);

-- 이 미션이 valid_date 하루 동안 목표를 지켰는가. 수령(complete_mission)과 자동 정산
-- (settle_missions)이 같은 기준을 쓰도록 한 곳에 둔다. 기록이 없으면 0으로 본다 —
-- 하루 종일 동기화를 안 한 것과 진짜 0분을 구분할 수 없다(ADR-25).
create or replace function mission_achieved(p_user_id uuid, p_mission_id uuid)
returns boolean
language sql
stable
as $$
  select case m.metric
    when 'pet_calls' then
      coalesce((select calls from daily_pet_calls
                where user_id = p_user_id and usage_date = m.valid_date), 0) <= m.target_count
    else
      coalesce((select sum(minutes) from daily_usage du
                where du.user_id = p_user_id and du.usage_date = m.valid_date
                  and (m.app_id is null or du.app_id = m.app_id)), 0) <= m.target_minutes
  end
  from missions m
  where m.id = p_mission_id
$$;

revoke execute on function mission_achieved(uuid, uuid) from public, anon, authenticated;

-- 수령: 하루가 끝난 뒤에만, 목표를 지켰을 때만 코인을 준다. 이전에는 아무 검증 없이
-- 지급됐다. 함수 이름은 FE 호환을 위해 유지한다.
create or replace function complete_mission(p_user_mission_id uuid, p_request_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_reward int;
  v_mission_id uuid;
  v_valid_date date;
begin
  -- 같은 사용자의 코인 변경을 직렬화한다 (ADR-008).
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

  -- 멱등: 이미 처리된 요청이면 아무것도 안 하고 끝
  if exists (select 1 from coin_ledger where request_id = p_request_id) then
    return;
  end if;

  select m.reward_coins, m.id, m.valid_date into v_reward, v_mission_id, v_valid_date
  from user_missions um
  join missions m on m.id = um.mission_id
  where um.id = p_user_mission_id
    and um.user_id = auth.uid()
    and um.status = 'in_progress'
    and m.type = 'daily';

  if v_reward is null then
    raise exception 'mission not found or already completed';
  end if;

  if v_valid_date >= (now() at time zone 'Asia/Seoul')::date then
    raise exception 'mission not finished';
  end if;

  if not mission_achieved(auth.uid(), v_mission_id) then
    raise exception 'mission target not met';
  end if;

  -- status 조건을 함께 걸어 두 번째 호출이 덮어쓰지 못하게 한다
  update user_missions
  set status = 'completed', coins_earned = v_reward, completed_at = now()
  where id = p_user_mission_id
    and status = 'in_progress';

  if not found then
    raise exception 'mission not found or already completed';
  end if;

  insert into coin_ledger (user_id, amount, reason, request_id)
  values (auth.uid(), v_reward, 'mission_complete', p_request_id);
end;
$$;

-- 자동 정산: 하루가 끝난 미션 중 아직 in_progress인 것을 판정한다. 지켰으면 수령한 것과
-- 같은 코인을 주고, 못 지켰으면 failed(FR-067). 정산 시점을 늦추려면(유예) 아래
-- valid_date 조건에서 v_today에 유예 일수를 빼면 된다(ADR-25).
--
-- 코인 멱등키는 user_mission id에서 결정적으로 만든다 — 재실행돼도 unique 제약이
-- 이중 지급을 막는다. 수령과 겹쳐도 update의 status 조건이 한쪽만 통과시킨다.
create or replace function settle_missions()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  r record;
  v_today date := (now() at time zone 'Asia/Seoul')::date;
begin
  perform pg_advisory_xact_lock(hashtextextended('settle_missions', 0));

  for r in
    select um.id as um_id, um.user_id, m.id as mission_id, m.reward_coins
    from user_missions um
    join missions m on m.id = um.mission_id
    where um.status = 'in_progress'
      and m.type = 'daily'
      and m.valid_date < v_today
  loop
    if mission_achieved(r.user_id, r.mission_id) then
      update user_missions
      set status = 'completed', coins_earned = r.reward_coins, completed_at = now()
      where id = r.um_id and status = 'in_progress';

      if found then
        insert into coin_ledger (user_id, amount, reason, request_id)
        values (r.user_id, r.reward_coins, 'mission_settle', md5('settle:' || r.um_id)::uuid);
      end if;
    else
      update user_missions set status = 'failed'
      where id = r.um_id and status = 'in_progress';
    end if;
  end loop;
end;
$$;

-- 모든 유저의 코인을 움직이는 배치라 로그인한 사용자가 RPC로 부르면 안 된다.
revoke execute on function settle_missions() from public, anon, authenticated;

-- 오늘(KST)의 미션 3장: 활성 앱 중 어제 사용량 상위 2개의 앱별 미션 + 펫 호출 미션.
-- 목표는 ADR-005 공식(어제 사용량 - 10분, 최소 15분)을 앱별로 적용하고, 펫 호출은
-- 어제 횟수 - 1에 최소 2회다. 보상은 전부 20코인. 활성 앱이 없는 유저는 앱 미션 없이
-- 펫 호출 미션만 받는다.
create or replace function generate_daily_missions()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user record;
  v_app record;
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_yesterday date := v_today - 1;
  v_target int;
  v_calls int;
  v_mission_id uuid;
begin
  -- 배치 전체를 직렬화한다 — 겹쳐 돌면 유저별 "오늘 미션 있나" 체크가 레이스로
  -- 중복 생성될 수 있다.
  perform pg_advisory_xact_lock(hashtextextended('generate_daily_missions', 0));

  for v_user in select id from profiles loop
    if exists (
      select 1 from user_missions um
      join missions m on m.id = um.mission_id
      where um.user_id = v_user.id and m.type = 'daily' and m.valid_date = v_today
    ) then
      continue; -- 오늘 미션 이미 있음 — 재실행 안전장치
    end if;

    for v_app in
      select da.id, da.display_name, coalesce(sum(du.minutes), 0)::int as minutes
      from user_detected_apps uda
      join detected_apps da on da.id = uda.app_id
      left join daily_usage du
        on du.user_id = uda.user_id and du.app_id = da.id and du.usage_date = v_yesterday
      where uda.user_id = v_user.id and uda.is_enabled
      group by da.id, da.display_name
      order by minutes desc, da.display_name
      limit 2
    loop
      v_target := greatest(v_app.minutes - 10, 15);

      insert into missions (type, title, target_minutes, reward_coins, valid_date, app_id, metric)
      values ('daily', v_app.display_name || ' ' || v_target || '분 이내로 보기', v_target, 20,
              v_today, v_app.id, 'usage_minutes')
      returning id into v_mission_id;

      insert into user_missions (user_id, mission_id, status)
      values (v_user.id, v_mission_id, 'in_progress');
    end loop;

    select coalesce(calls, 0) into v_calls
    from daily_pet_calls where user_id = v_user.id and usage_date = v_yesterday;
    v_target := greatest(coalesce(v_calls, 0) - 1, 2);

    insert into missions (type, title, target_count, reward_coins, valid_date, metric)
    values ('daily', '오늘 펫 ' || v_target || '회 이하로 보기', v_target, 20, v_today, 'pet_calls')
    returning id into v_mission_id;

    insert into user_missions (user_id, mission_id, status)
    values (v_user.id, v_mission_id, 'in_progress');
  end loop;
end;
$$;

-- 알림 대상 쿼리도 미션 날짜(KST)에 맞춘다. 기존에는 current_date(UTC)였다.
-- create or replace는 기존 grant(service_role만)를 그대로 둔다.
create or replace function users_to_notify_today()
returns table(user_id uuid, fcm_token text)
language sql
stable
as $$
  select p.id, p.fcm_token
  from profiles p
  join user_missions um on um.user_id = p.id
  join missions m on m.id = um.mission_id
    and m.type = 'daily' and m.valid_date = (now() at time zone 'Asia/Seoul')::date
  left join notification_settings ns on ns.user_id = p.id
  where coalesce(ns.mission_alert, true)
    and p.fcm_token is not null
    and p.fcm_token <> ''
$$;

-- cron: 06:00 KST에 전날 미션 정산 → 새 미션 생성 순서로 한 job에서 돌리고, 알림은
-- 5분 뒤에 보낸다(원래 ADR-005·ADR-18이 의도한 시각). 알림 job의 명령은 Vault
-- 참조를 포함해서 다시 쓰지 않고 스케줄만 바꾼다. job이 없으면 아무 일도 안 한다.
select cron.schedule(
  'generate-daily-missions',
  '0 21 * * *',
  $$select settle_missions(); select generate_daily_missions()$$
);

select cron.alter_job(jobid, schedule := '5 21 * * *')
from cron.job
where jobname = 'send-mission-notifications';
