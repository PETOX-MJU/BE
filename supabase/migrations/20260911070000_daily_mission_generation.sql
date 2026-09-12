-- ADR-005: pg_cron이 매일 06:00 이 함수를 호출해 전체 유저의 오늘 미션을 미리 생성한다.
-- 규칙: 어제 총 사용시간 - 10분, 최소 15분. FR-057(미션 알림, P0)이 "알림 내용이 앱을 열기
-- 전에 이미 있어야 함"을 요구해서 온디맨드가 아니라 배치로 간다.
-- 이미 오늘 미션이 있는 유저는 건너뛴다 — 배치가 중복 실행돼도 안전하게(멱등).
-- https://app.notion.com/p/3d873962994081b28706c6b2c4228478

create or replace function generate_daily_missions()
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user record;
  v_yesterday date := current_date - 1;
  v_yesterday_minutes int;
  v_target int;
  v_mission_id uuid;
begin
  for v_user in select id from profiles loop
    if exists (
      select 1 from user_missions um
      join missions m on m.id = um.mission_id
      where um.user_id = v_user.id and m.type = 'daily' and m.valid_date = current_date
    ) then
      continue; -- 오늘 미션 이미 있음 — 재실행 안전장치
    end if;

    select coalesce(sum(minutes), 0) into v_yesterday_minutes
    from daily_usage
    where user_id = v_user.id and usage_date = v_yesterday;

    v_target := greatest(v_yesterday_minutes - 10, 15);

    insert into missions (type, title, target_minutes, reward_coins, valid_date)
    values ('daily', '오늘은 ' || v_target || '분 이내로 줄이기', v_target, 20, current_date)
    returning id into v_mission_id;

    insert into user_missions (user_id, mission_id, status)
    values (v_user.id, v_mission_id, 'in_progress');
  end loop;
end;
$$;

create extension if not exists pg_cron with schema extensions;

select cron.schedule(
  'generate-daily-missions',
  '0 6 * * *',
  $$select generate_daily_missions()$$
);
