-- 펫 슬롯 아이템과 슬롯 한도 트리거의 동시성 구멍.
--
-- 1) 상점에 pet_slot 아이템이 없어 FE의 "두 번째 펫 추가" 흐름이 구매 단계에서 멈춘다.
--    운영에는 대시보드로 먼저 넣었으므로(30코인) 이미 있으면 건너뛴다.
insert into items (name, type, price_coins)
select '펫 슬롯', 'pet_slot', 30
where not exists (select 1 from items where type = 'pet_slot');

-- 2) 트리거가 펫 수를 센 뒤 insert하는 사이에 잠금이 없어, 같은 사용자의 insert 두 개가
--    동시에 오면 둘 다 한도 미만으로 보고 들어간다(ADR-22에 남겨 둔 구멍).
--    코인 RPC와 같은 사용자 단위 advisory lock(ADR-008)으로 직렬화한다. 같은 키라
--    buy_item(펫 슬롯 구매)과 펫 추가도 서로 순서대로 처리된다.
create or replace function enforce_pet_slot_limit()
returns trigger
language plpgsql
as $$
begin
  perform pg_advisory_xact_lock(hashtextextended(new.user_id::text, 0));

  if (select count(*) from pets where user_id = new.user_id)
     >= coalesce((select pet_slot_limit from profiles where id = new.user_id), 1) then
    raise exception 'pet slot limit reached';
  end if;
  return new;
end;
$$;
