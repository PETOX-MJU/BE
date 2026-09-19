-- ADR-22: RLS update 정책은 행 단위라 본인 행이면 모든 컬럼을 고칠 수 있었다.
-- 코인·성장이 걸린 컬럼(pets.level/affection, profiles.pet_slot_limit,
-- user_items.item_id)은 서버 RPC만 바꿀 수 있어야 하므로, 테이블 권한을 회수하고
-- 클라이언트가 실제로 써야 하는 컬럼만 다시 grant한다. security definer RPC는
-- 함수 소유자 권한으로 돌아서 영향받지 않는다.
--
-- 이후 추가되는 컬럼은 기본이 쓰기 불가다 — 클라이언트에 열어야 하면 여기에 추가할 것.

-- pets: level/affection은 insert로도 못 넣게 insert도 컬럼 단위로 제한한다.
revoke insert, update on pets from authenticated;
grant insert (id, user_id, name, is_default, source_photo_url, pixel_image_url)
  on pets to authenticated;
grant update (name, is_default, source_photo_url, pixel_image_url)
  on pets to authenticated;

revoke update on profiles from authenticated;
grant update (goal_minutes, focus_start, focus_end, bedtime, nickname, fcm_token)
  on profiles to authenticated;

revoke update on user_items from authenticated;
grant update (is_equipped) on user_items to authenticated;

-- 펫 수는 profiles.pet_slot_limit(코인으로 확장)을 넘을 수 없다. 컬럼 권한으로는
-- 개수를 못 막아서 트리거로 건다. invoker 권한이라 RLS가 적용돼 본인 행만 센다.
-- 동시 insert에서는 한도를 넘길 수 있다(advisory lock 미적용, ADR-22).
create or replace function enforce_pet_slot_limit()
returns trigger
language plpgsql
as $$
begin
  if (select count(*) from pets where user_id = new.user_id)
     >= coalesce((select pet_slot_limit from profiles where id = new.user_id), 1) then
    raise exception 'pet slot limit reached';
  end if;
  return new;
end;
$$;

create trigger pets_enforce_slot_limit
  before insert on pets
  for each row execute function enforce_pet_slot_limit();
