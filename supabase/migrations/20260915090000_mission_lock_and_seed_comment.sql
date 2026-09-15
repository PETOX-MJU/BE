-- 이슈 #4(PR #3 리뷰 후속) 처리.
--
-- 1) generate_daily_missions()도 buy_item/complete_mission과 같은 유형의 구멍이
--    있었다: 유저마다 "오늘 미션 있나?"(select) 확인 후 없으면 insert인데 그
--    사이에 잠금이 없다. 이 배치가 겹쳐서 두 번 돌면(예: 수동 재실행이 스케줄
--    실행과 겹침) 같은 유저에게 오늘 미션이 중복 생성될 수 있고, 이를 막는
--    유니크 제약도 없다. buy_item과 같은 패턴으로 배치 전체를 advisory lock
--    하나로 직렬화한다 — 고정 키라 두 번째 실행은 첫 번째가 끝날 때까지
--    대기했다가, 그때는 이미 첫 번째가 만든 미션을 보고 건너뛴다.
--
-- 2) hashtextextended(text, N)의 N은 "modulus"가 아니라 seed다(PostgreSQL
--    공식 문서: 두 번째 인자가 0이면 하위 32비트가 기존 hashtext()와 같은 값이
--    되고, 그 외 값이면 결과를 섞는 용도). buy_item/complete_mission이 고정
--    시드 0을 쓰는 이유를 주석으로 남긴다.

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
  -- 배치 전체를 직렬화한다 — 이 함수가 겹쳐 돌면 유저별 "오늘 미션 있나" 체크가
  -- 레이스로 중복 생성될 수 있다(buy_item과 같은 유형).
  perform pg_advisory_xact_lock(hashtextextended('generate_daily_missions', 0));

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

create or replace function complete_mission(p_user_mission_id uuid, p_request_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_reward int;
begin
  -- 같은 사용자의 코인 변경을 직렬화한다 (ADR-008). 두 번째 인자 0은
  -- "modulus"가 아니라 seed — 0을 주면 hashtext()와 같은 하위 32비트를 쓰되
  -- 반환형은 64비트라, auth.uid()를 advisory lock 키(bigint) 하나로 결정적으로
  -- 바꾸는 용도로 충분하다.
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

  -- 멱등: 이미 처리된 요청이면 아무것도 안 하고 끝
  if exists (select 1 from coin_ledger where request_id = p_request_id) then
    return;
  end if;

  select m.reward_coins into v_reward
  from user_missions um
  join missions m on m.id = um.mission_id
  where um.id = p_user_mission_id
    and um.user_id = auth.uid()
    and um.status = 'in_progress';

  if v_reward is null then
    raise exception 'mission not found or already completed';
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

create or replace function buy_item(p_item_id uuid, p_request_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_price int;
  v_type text;
  v_balance int;
begin
  -- 잔액을 읽기 전에 잠근다. 이 사용자의 다른 구매는 여기서 대기한다 (ADR-008).
  -- 두 번째 인자 0은 seed(고정값으로 결정적인 64비트 키를 얻기 위함) — modulus 아님.
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

  if exists (select 1 from coin_ledger where request_id = p_request_id) then
    return;
  end if;

  select price_coins, type into v_price, v_type from items where id = p_item_id;
  if v_price is null then
    raise exception 'item not found';
  end if;

  select coalesce(sum(amount), 0) into v_balance
  from coin_ledger where user_id = auth.uid();

  if v_balance < v_price then
    raise exception '코인이 부족합니다';
  end if;

  insert into coin_ledger (user_id, amount, reason, request_id)
  values (auth.uid(), -v_price, 'item_purchase', p_request_id);

  -- pet_slot 아이템은 보유 아이템이 아니라 슬롯 한도 증가로 처리
  if v_type = 'pet_slot' then
    update profiles set pet_slot_limit = pet_slot_limit + 1 where id = auth.uid();
  else
    insert into user_items (user_id, item_id) values (auth.uid(), p_item_id);
  end if;
end;
$$;
