-- ADR-39: 미션 판정을 서버로 되돌린다(ADR-37을 뒤집는다). FE가 동의받은 사용자의
-- 앱별 하루 합계를 daily_usage에 올리고, 동의 화면도 "서버가 판정해 코인을 준다"고
-- 안내한다. 폰 판정기(Missions.kt)는 FE 어디에도 연결돼 있지 않다.
--
-- ADR-37이 함수·테이블을 지우지 않고 스케줄만 껐으므로, 스케줄만 다시 켠다.
-- 정산 00:05, 알림 06:05(KST)는 ADR-37 직전 그대로다. 생성은 날짜가 바뀌자마자
-- 새 미션이 보이도록 정산 직후 00:10으로 옮긴다(ADR-40).

-- ADR-40: 사용시간 미션을 "앱별 어제-10분" 2개에서 "감지 앱 합계 ≤ 목표 시간" 1개로 바꾼다.
-- 목표는 생성 시점의 profiles.goal_minutes로 고정된다. 펫 호출 미션은 그대로다.
-- 판정(mission_achieved)은 app_id가 null이면 그날 올라온 daily_usage를 모두 더한다.
create or replace function generate_daily_missions()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user record;
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_yesterday date := v_today - 1;
  v_target int;
  v_calls int;
  v_mission_id uuid;
begin
  -- 배치 전체를 직렬화한다 — 겹쳐 돌면 유저별 "오늘 미션 있나" 체크가 레이스로
  -- 중복 생성될 수 있다.
  perform pg_advisory_xact_lock(hashtextextended('generate_daily_missions', 0));

  for v_user in select id, goal_minutes from profiles loop
    if exists (
      select 1 from user_missions um
      join missions m on m.id = um.mission_id
      where um.user_id = v_user.id and m.type = 'daily' and m.valid_date = v_today
    ) then
      continue; -- 오늘 미션 이미 있음 — 재실행 안전장치
    end if;

    v_target := coalesce(v_user.goal_minutes, 60);

    insert into missions (type, title, target_minutes, reward_coins, valid_date, metric)
    values ('daily', '숏폼 ' || v_target || '분 이내로 보기', v_target, 20, v_today, 'usage_minutes')
    returning id into v_mission_id;

    insert into user_missions (user_id, mission_id, status)
    values (v_user.id, v_mission_id, 'in_progress');

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

select cron.schedule('generate-daily-missions', '10 15 * * *', $$select generate_daily_missions()$$);
select cron.schedule('settle-missions', '5 15 * * *', $$select settle_missions()$$);
select cron.schedule(
  'send-mission-notifications',
  '5 21 * * *',
  $$
  select net.http_post(
    url := (
      select decrypted_secret from vault.decrypted_secrets
      where name = 'send_mission_notifications_url'
    ),
    headers := jsonb_build_object(
      'apikey',
      (
        select decrypted_secret from vault.decrypted_secrets
        where name = 'cron_secret_key'
      ),
      'Content-Type', 'application/json'
    ),
    body := '{}'::jsonb
  )
  $$
);

-- 서버 정산과 함께 열려 있으면 같은 날 코인이 두 번 나간다. 되돌릴 수 있게 함수는 남긴다.
revoke execute on function claim_mission_reward(text, date) from authenticated;

-- 배포한 날에도 오늘 미션이 있게 한다. 오늘 미션이 이미 있는 사용자는 건너뛴다.
select generate_daily_missions();
