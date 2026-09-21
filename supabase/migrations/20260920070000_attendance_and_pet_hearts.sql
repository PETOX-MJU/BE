-- ADR-27/28: 출석체크(연속 출석 보너스)와 하트(애착도 +5).
-- 두 기능 모두 코인·성장 값이 걸려 있어서 클라이언트가 직접 쓰지 못하고 RPC만 쓴다.
-- 하루의 기준은 KST 날짜다(ADR-24와 같은 가정).

-- 출석: insert 정책을 두지 않는다 — check_in()만 쓸 수 있어서 날짜를 속일 수 없다.
create table attendance (
  user_id uuid not null references auth.users(id) on delete cascade,
  attended_on date not null,
  primary key (user_id, attended_on)
);

alter table attendance enable row level security;
create policy "own attendance select" on attendance for select using (user_id = auth.uid());

-- 출석하면 5코인, 연속 7일째마다 30코인을 더 준다. 하루라도 빠지면 연속은 1부터 다시 센다.
-- 코인 멱등키를 (유저, 날짜)에서 결정적으로 만들어 재호출해도 이중 지급이 없다.
create or replace function check_in()
returns table(streak int, coins_awarded int)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_today date := (now() at time zone 'Asia/Seoul')::date;
  v_inserted int;
  v_streak int;
  v_coins int := 0;
begin
  -- 같은 사용자의 코인 변경을 직렬화한다 (ADR-008).
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

  insert into attendance (user_id, attended_on) values (auth.uid(), v_today)
  on conflict do nothing;
  get diagnostics v_inserted = row_count;

  -- 오늘부터 거꾸로 날짜가 이어지는 행만 센다: 날짜 + 순번이 같으면 끊김 없이 이어진 것이다.
  select count(*) into v_streak
  from (
    select attended_on + (row_number() over (order by attended_on desc))::int as k
    from attendance
    where user_id = auth.uid() and attended_on <= v_today
  ) t
  where t.k = v_today + 1;

  if v_inserted = 1 then
    v_coins := 5 + case when v_streak % 7 = 0 then 30 else 0 end;
    -- 날짜를 to_char로 고정한다. date를 그냥 text로 이어붙이면 세션의 DateStyle
    -- 설정을 타는데(security definer는 이 설정을 초기화하지 않는다), 키 문자열이
    -- 달라지는 순간 unique 제약이 안 걸려 같은 날 이중 지급이 된다.
    insert into coin_ledger (user_id, amount, reason, request_id)
    values (auth.uid(), v_coins, 'attendance',
            md5('checkin:' || auth.uid() || ':' || to_char(v_today, 'YYYYMMDD'))::uuid);
  end if;

  return query select v_streak, v_coins;
end;
$$;

-- 저장소의 다른 RPC와 같이 권한을 명시한다. 이게 없으면 CREATE FUNCTION이 PUBLIC에
-- 자동으로 주는 execute에 기대게 되고, anon도 호출할 수 있다. 지금 anon이 막히는
-- 것은 auth.uid()가 NULL이라 NOT NULL 위반으로 터지기 때문이지 의도한 방어가 아니다.
revoke execute on function check_in() from public, anon;
grant execute on function check_in() to authenticated;

-- 하트: 클라이언트가 pets.affection을 직접 못 올리므로(ADR-22) 이 RPC가 유일한 경로다.
-- 한 번에 +5, 펫당 하루 +50까지, 애착도는 100을 넘지 않는다(FR-034). 100 제한은 check
-- 제약이 아니라 여기서만 강제한다 — 기존 행이 범위를 벗어났으면 제약 추가가 실패하기 때문이다.
create table pet_interactions (
  pet_id uuid not null references pets(id) on delete cascade,
  interacted_on date not null,
  gained int not null default 0 check (gained >= 0),
  primary key (pet_id, interacted_on)
);

alter table pet_interactions enable row level security;
create policy "own pet interactions select" on pet_interactions for select
  using (exists (select 1 from pets p where p.id = pet_id and p.user_id = auth.uid()));

-- 출력 컬럼 이름을 affection/gained로 두면 테이블 컬럼과 겹쳐 모호성 오류가 난다.
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
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

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

revoke execute on function pet_interact(uuid) from public, anon;
grant execute on function pet_interact(uuid) to authenticated;
