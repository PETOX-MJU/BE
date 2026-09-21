-- 자동 정산을 "하루가 끝나는 순간"으로 옮긴다 — 판정 대상은 방금 끝난 어제 하루다.
--
-- 20260919090000이 유예 1일(D+2 정산)을 넣었는데, 그건 ADR-25에서 이미 내려진
-- 결정을 뒤집은 것이었다. ADR-25는 유예 1일을 선택지로 비교한 뒤 "다음 날 바로"를
-- 채택했고("미션이 하루 기준이라 자동 정산이 맞다"), 여기서 한 발 더 나아가
-- 정산 시각 자체를 아침 06:00이 아니라 날짜가 바뀌는 시점으로 당긴다.
--
-- 미션 생성·알림 cron은 그대로 KST 06:00/06:05다(ADR-005·ADR-18). 정산만 분리해
-- 앞당기는 것이고, 정산과 생성은 건드리는 행이 겹치지 않아 순서 의존이 없다.
--
-- 20260919090000의 나머지 두 가지는 유예와 무관하게 유효해서 그대로 둔다.
--   - 오래된 미션을 지급 없이 failed로 정리하는 하한. mission_achieved는 기록이
--     없으면 "지켰다"로 보는데 오래된 미션은 그 기록이 없는 게 정상이라, 하한이
--     없으면 배포 직후 첫 실행에서 미수령 미션이 한꺼번에 지급된다.
--   - complete_mission이 이미 정산된 미션을 예외 없이 끝내는 것(별도 함수라 무관).
--     자정 정산에서는 수령 창이 사실상 0이라, 이 처리가 없으면 FE의 "받기"는
--     항상 에러가 난다. 보조 경로로 남기려면 반드시 필요하다.
--
-- 머지된 마이그레이션은 과거 상태 기록으로 남기고 고치지 않는다(20260916090000과
-- 같은 방식) — 이 파일이 사실상 그 함수를 고치는 마이그레이션이다.

-- valid_date를 두 구간으로 나눈다.
--   어제        판정해서 지급 또는 failed — 방금 끝난 하루다
--   그보다 이전  지급 없이 failed
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

  -- 하루가 끝난 지 이틀 넘은 미션은 판정 근거를 믿을 수 없으므로 지급 없이 정리한다.
  update user_missions um
  set status = 'failed'
  from missions m
  where m.id = um.mission_id
    and um.status = 'in_progress'
    and m.type = 'daily'
    and m.valid_date < v_today - 1;

  for r in
    select um.id as um_id, um.user_id, m.id as mission_id, m.reward_coins
    from user_missions um
    join missions m on m.id = um.mission_id
    where um.status = 'in_progress'
      and m.type = 'daily'
      and m.valid_date = v_today - 1
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

-- 정산 job을 KST 06:00(UTC 21:00)에서 날짜가 바뀌는 시점으로 옮긴다.
-- UTC 15:05 = KST 00:05. 정각이 아니라 5분 뒤인 이유는 v_today를 함수 안에서
-- (now() at time zone 'Asia/Seoul')::date로 구하기 때문이다. 정각에 걸면 DB 시계가
-- 조금만 뒤처져도 v_today가 아직 어제로 읽혀 valid_date = v_today - 1이 그제를
-- 가리키고, 정작 방금 끝난 하루는 다음 실행에서 하한에 걸려 지급 없이 failed가 된다.
-- 같은 이름으로 다시 부르면 cron.schedule이 기존 job을 덮어쓴다.
select cron.schedule('settle-missions', '5 15 * * *', $$select settle_missions()$$);
