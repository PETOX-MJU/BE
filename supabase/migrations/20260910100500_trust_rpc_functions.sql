-- ADR-004: 미션 보상·아이템(펫 슬롯 포함) 구매는 RPC로 처리한다.
-- security definer라 RLS를 우회해 coin_ledger·user_items·profiles.pet_slot_limit에 쓸 수 있고,
-- 그래서 이 함수들이 그 테이블들의 유일한 쓰기 경로다 — 클라이언트가 "코인 확인"을 건너뛸 수 없다.
-- request_id로 멱등 — 같은 요청이 재시도돼도 정확히 한 번만 처리된다.
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

  update user_missions
  set status = 'completed', coins_earned = v_reward, completed_at = now()
  where id = p_user_mission_id;

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
