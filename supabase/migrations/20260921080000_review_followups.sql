-- PR #22·#24·#25·#26 리뷰에서 "사소"로 분류하고 미뤄뒀던 3건.
-- 머지된 마이그레이션은 과거 상태 기록으로 남기고 여기서 교체한다.
--
-- 1) complete_mission이 daily가 아닌 미션을 조용히 'mission not found'로 떨어뜨린다
-- 2) pet_interact가 코인을 건드리지 않는데 코인 락을 잡는다
-- 3) pet_interactions RLS 정책의 pet_id가 비한정 참조다

-- ── 1. weekly 미션 수령 시도를 조용히 삼키지 않는다 ──────────────────────
--
-- 기존에는 select 조건에 m.type = 'daily'가 들어가 있어서, weekly 미션을 수령하면
-- 행을 못 찾아 'mission not found'가 났다. 미션이 실제로 있는데 없다고 말하는 셈이라
-- FR-070(주간 미션, P2)을 넣을 때 원인을 찾기 어렵다.
--
-- weekly를 지원하도록 만들지는 않는다. mission_achieved가 m.valid_date 하루만 보고
-- 판정하므로 주간 집계 규칙이 정해져야 판정할 수 있고, 그건 이 변경의 범위가 아니다.
-- 대신 지원하지 않는다는 것을 그대로 말한다.
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
  v_status text;
  v_type text;
begin
  -- 같은 사용자의 코인 변경을 직렬화한다 (ADR-008).
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

  -- 멱등: 이미 처리된 요청이면 아무것도 안 하고 끝
  if exists (select 1 from coin_ledger where request_id = p_request_id) then
    return;
  end if;

  select m.reward_coins, m.id, m.valid_date, um.status, m.type
    into v_reward, v_mission_id, v_valid_date, v_status, v_type
  from user_missions um
  join missions m on m.id = um.mission_id
  where um.id = p_user_mission_id
    and um.user_id = auth.uid();

  if v_status is null then
    raise exception 'mission not found';
  end if;

  if v_type <> 'daily' then
    raise exception 'only daily missions can be claimed';
  end if;

  -- 자동 정산(settle_missions)이 먼저 지급한 경우다. 코인은 이미 들어가 있으므로
  -- 여기서 예외를 내면 FE는 "성공했는데 에러"를 보게 된다. 조용히 끝낸다 —
  -- request_id 멱등 처리와 같은 성격이다.
  if v_status = 'completed' then
    return;
  end if;

  if v_status <> 'in_progress' then
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

-- ── 2. 하트는 코인 락이 아니라 펫 단위 락을 잡는다 ──────────────────────
--
-- pet_interact는 coin_ledger를 건드리지 않는데 buy_item·complete_mission과 같은
-- 키(auth.uid())로 잠가서, 하트를 탭하는 동안 같은 사용자의 구매가 대기했다.
-- 잠가야 하는 건 코인이 아니라 그 펫의 affection이다 — 읽고(v_affection) 계산해서
-- (v_gain) 쓰는 구간이라 잠금 자체는 필요하다. 없으면 동시 탭 두 건이 둘 다
-- affection=95를 읽고 각자 +5를 해서 100을 넘긴다.
--
-- 키를 펫 id로 바꾸면 경합 대상만 직렬화되고 코인 경로와 분리된다.
create or replace function pet_interact(p_pet_id uuid)
returns table(new_affection int, hearts_gained int)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_affection int;
  v_gained_today int;
  v_gain int;
begin
  perform pg_advisory_xact_lock(hashtextextended('pet_interact:' || p_pet_id::text, 0));

  select p.affection into v_affection
  from pets p where p.id = p_pet_id and p.user_id = auth.uid();
  if not found then
    raise exception 'pet not found';
  end if;

  select gained into v_gained_today
  from pet_interactions where pet_id = p_pet_id and interacted_on = v_today;

  v_gain := greatest(0, least(5, 50 - coalesce(v_gained_today, 0), 100 - v_affection));

  if v_gain > 0 then
    update pets set affection = affection + v_gain where id = p_pet_id;
    insert into pet_interactions (pet_id, interacted_on, gained)
    values (p_pet_id, v_today, v_gain)
    on conflict (pet_id, interacted_on)
    do update set gained = pet_interactions.gained + excluded.gained;
  end if;

  return query select v_affection + v_gain, v_gain;
end;
$$;

-- ── 3. RLS 정책의 pet_id를 한정 참조로 바꾼다 ───────────────────────────
--
-- where p.id = pet_id 는 pets에 pet_id 컬럼이 없어서 지금은 바깥 테이블로 해석된다.
-- pets에 같은 이름 컬럼이 생기면 조용히 그쪽으로 붙어 정책이 항상 참이 될 수 있다.
alter policy "own pet interactions select" on pet_interactions
  using (exists (
    select 1 from pets p
    where p.id = pet_interactions.pet_id and p.user_id = auth.uid()
  ));
