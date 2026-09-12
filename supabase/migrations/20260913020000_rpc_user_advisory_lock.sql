-- ADR-008: buy_item·complete_mission에 사용자 단위 advisory lock을 건다.
--
-- 문제: 두 함수 모두 "select로 읽고 → 검사하고 → insert/update" 순서인데 그 사이에
-- 잠금이 없었다. request_id unique는 같은 요청의 재시도만 막지, request_id가 다른
-- 동시 요청 두 건은 못 막는다. 테스트로 실증됨(tests/test_rpc_trust.py):
--   - buy_item:        잔액 100에 60짜리 두 건 동시 → 잔액 -20
--   - complete_mission: 같은 미션 두 건 동시 → 보상 50이 100으로 이중 지급
--
-- 해법: 함수 진입 직후 auth.uid() 해시로 트랜잭션 범위 advisory lock을 잡는다.
-- 같은 사용자의 코인 변경만 직렬화되고 다른 사용자는 막히지 않는다. 트랜잭션이
-- 끝나면 자동 해제되므로 해제를 잊을 수 없다.
--
-- 한계: advisory lock은 DB 인스턴스 범위다. 읽기 레플리카로 쓰기를 분산하거나
-- 샤딩하면 무효가 된다. 지금 규모(ADR-001: 사용자 수십 명, 단일 인스턴스)에서는
-- 유효하고, 그 전제가 바뀌면 재검토 대상이다.
--
-- https://app.notion.com/p/3d7739629940818eab12fe9fecf42db3

create or replace function complete_mission(p_user_mission_id uuid, p_request_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_reward int;
begin
  -- 같은 사용자의 코인 변경을 직렬화한다 (ADR-008)
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
  -- 잔액을 읽기 전에 잠근다. 이 사용자의 다른 구매는 여기서 대기한다 (ADR-008)
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

grant execute on function complete_mission(uuid, uuid) to authenticated;
grant execute on function buy_item(uuid, uuid) to authenticated;
