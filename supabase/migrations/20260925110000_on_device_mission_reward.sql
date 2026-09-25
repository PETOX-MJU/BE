-- ADR-37: 미션 판정은 폰 분석기(AI 레포 kotlin_port Missions.kt)가 한다. 사용시간은 서버로
-- 오지 않으므로 서버는 판정하지 않고, 폰이 성공이라고 알린 미션에 코인만 준다.
--
-- 서버는 성공 여부를 검증할 수 없다. 대신 조작 상한을 묶는다: 같은 날짜·종류는 한 번,
-- 날짜는 최근 7일 이내이면서 가입일 이후. 하루 최대 40코인이다.
create or replace function claim_mission_reward(p_kind text, p_date date)
returns int
language plpgsql
security definer
set search_path = public
as $$
declare
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_joined date;
  v_inserted int;
begin
  -- 폰 분석기의 MissionKind(DAILY·NIGHT)와 같은 두 종류다.
  if p_kind is null or p_kind not in ('daily', 'night') then
    raise exception 'invalid mission kind';
  end if;

  select (created_at at time zone 'Asia/Seoul')::date into v_joined
  from profiles where id = auth.uid();

  if p_date is null or p_date > v_today or p_date < greatest(v_today - 7, v_joined) then
    raise exception 'mission date out of range';
  end if;

  -- 멱등키를 (사용자, 종류, 날짜)에서 결정적으로 만들어 재호출해도 한 번만 지급된다(check_in과 같은 방식).
  -- 날짜는 to_char로 고정한다. date를 text로 이어붙이면 세션 DateStyle을 타서 키가 달라질 수 있다.
  insert into coin_ledger (user_id, amount, reason, request_id)
  values (auth.uid(), 20, 'mission_reward',
          md5('mission:' || auth.uid() || ':' || p_kind || ':' || to_char(p_date, 'YYYYMMDD'))::uuid)
  on conflict (request_id) do nothing;
  get diagnostics v_inserted = row_count;

  return 20 * v_inserted;
end;
$$;

revoke execute on function claim_mission_reward(text, date) from public, anon;
grant execute on function claim_mission_reward(text, date) to authenticated;

-- 서버 미션(ADR-005·25·26)과 서버 미션 알림(ADR-18)은 더 이상 쓰지 않는다. 되돌릴 수 있게
-- 함수·테이블은 남기고 스케줄만 끈다.
select cron.unschedule('generate-daily-missions');
select cron.unschedule('settle-missions');
select cron.unschedule('send-mission-notifications');
