-- 이슈 #15: 홈 화면 목업의 "테마"(방 배경)·"아이템"(가구: 침대·간식 놀이 세트·
-- 화분·선반)이 지금 CHECK 제약(clothing, pet_slot만 허용)에 막혀 애초에
-- insert가 거부됐다.
--
-- buy_item()(20260915090000)은 pet_slot만 특수 처리(profiles.pet_slot_limit
-- 증가)하고 나머진 전부 일반 경로(user_items insert)를 탄다. furniture·theme는
-- clothing과 성격이 같다 — "여러 개 보유 가능, 그중 하나를 적용"인데, 이건
-- user_items.is_equipped 컬럼이 이미 범용으로 처리하는 패턴이다(어떤 type이든
-- 클라이언트가 소유한 것 중 하나를 장착 상태로 토글). 그래서 buy_item()이나
-- RLS를 고칠 필요 없이 CHECK 제약만 넓히면 된다.

alter table items drop constraint items_type_check;
alter table items add constraint items_type_check
  check (type in ('clothing', 'pet_slot', 'furniture', 'theme'));
