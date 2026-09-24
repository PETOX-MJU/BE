-- ADR-34: 상점 테마 소속·순서 컬럼, 구매 규칙(중복·테마 먼저·순서대로), 카탈로그 시드.
-- FE(src/data/shop.ts)가 name 으로 서버 아이템과 짝을 지으므로 이름은 정확히 같아야 한다.

-- 1) 스키마 ------------------------------------------------------------------

-- 아이템이 속한 테마(테마 자신·테마 없는 아이템은 null)와 테마 안 순서(1부터)
alter table items add column theme_id uuid references items(id) on delete cascade;
alter table items add column sort_order int;
alter table items add constraint items_theme_order_check
  check ((theme_id is null) = (sort_order is null));

-- FE가 이름으로 짝을 지으므로 이름 중복 금지
create unique index items_name_key on items (name);
-- 한 테마 안에서 같은 순서 번호 금지
create unique index items_theme_order_key on items (theme_id, sort_order)
  where theme_id is not null;

-- 같은 아이템을 두 번 보유할 수 없다 (중복 구매의 최종 방어선)
alter table user_items add constraint user_items_user_item_key unique (user_id, item_id);

-- 2) 구매 RPC ----------------------------------------------------------------
-- 20260915090000 버전에 규칙 확인 3개만 추가. 잠금·멱등·잔액 확인 흐름은 그대로.

create or replace function buy_item(p_item_id uuid, p_request_id uuid)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_price int;
  v_type text;
  v_theme_id uuid;
  v_sort int;
  v_balance int;
begin
  -- 잔액을 읽기 전에 잠근다. 이 사용자의 다른 구매는 여기서 대기한다 (ADR-008).
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));

  if exists (select 1 from coin_ledger where request_id = p_request_id) then
    return;
  end if;

  select price_coins, type, theme_id, sort_order
    into v_price, v_type, v_theme_id, v_sort
  from items where id = p_item_id;
  if v_price is null then
    raise exception 'item not found';
  end if;

  if v_type <> 'pet_slot' then
    -- 규칙 1: 중복 구매 불가
    if exists (select 1 from user_items
               where user_id = auth.uid() and item_id = p_item_id) then
      raise exception '이미 보유한 아이템입니다';
    end if;

    if v_theme_id is not null then
      -- 규칙 2: 테마 먼저
      if not exists (select 1 from user_items
                     where user_id = auth.uid() and item_id = v_theme_id) then
        raise exception '테마를 먼저 구매해야 합니다';
      end if;

      -- 규칙 3: 앞 단계 아이템을 모두 가져야 함
      if exists (
        select 1 from items i
        where i.theme_id = v_theme_id
          and i.sort_order < v_sort
          and not exists (select 1 from user_items u
                          where u.user_id = auth.uid() and u.item_id = i.id)
      ) then
        raise exception '앞 단계 아이템을 먼저 구매해야 합니다';
      end if;
    end if;
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

-- 3) 시드 --------------------------------------------------------------------
-- 가격은 임시값(12). 확정되면 price_coins 만 수정.

insert into items (name, type, price_coins) values
  ('홈',     'theme', 12),
  ('해변',   'theme', 12),
  ('빙하',   'theme', 12),
  ('캠핑장', 'theme', 12)
on conflict (name) do nothing;

insert into items (name, type, price_coins, theme_id, sort_order)
select v.name, 'furniture', 12, t.id, v.sort_order
from (values
  ('홈',     '포근포근 방석',   1),
  ('홈',     '동글 화분',       2),
  ('홈',     '초록 선반',       3),
  ('홈',     '냠냠 놀이 세트',  4),
  ('해변',   '발바닥 파라솔',   1),
  ('해변',   '둥실 오리 튜브',  2),
  ('해변',   '고양이 돛단배',   3),
  ('해변',   '달빛 밤바다',     4),
  ('빙하',   '뒹굴 물범',       1),
  ('빙하',   '펭귄 바이킹선',   2),
  ('빙하',   '낚시왕 북극곰',   3),
  ('빙하',   '별빛 빙하',       4),
  ('캠핑장', '아늑한 텐트',     1),
  ('캠핑장', '타닥타닥 모닥불', 2),
  ('캠핑장', '도토리 다람쥐',   3),
  ('캠핑장', '별밤 캠핑',       4)
) as v(theme_name, name, sort_order)
join items t on t.name = v.theme_name and t.type = 'theme'
on conflict (name) do nothing;
