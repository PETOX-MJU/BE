-- ADR-36(#27): 캐릭터는 폰에서 만들고 폰에 저장한다. 폰을 바꾸면 사라지므로 AI 레포
-- pet_template 규칙("동기화·백업은 견종 + main·sub 스와치 이름만")대로 이 세 값만 백업한다.
-- 사진·캐릭터 이미지는 서버로 보내지 않는다.
--
-- 값 목록은 AI 레포 pet_template/breeds.json 의 breeds·swatches 키와 같아야 한다.
-- 틀린 이름은 breeds.json 에서 찾지 못해 캐릭터를 다시 만들 수 없으므로 저장 시점에 막는다.
-- 모두 null 허용이라 값을 보내지 않는 지금의 FE 는 그대로 동작한다.
alter table pets
  add column breed text
    check (breed in ('corgi', 'dachshund', 'golden', 'husky', 'shiba')),
  add column main_swatch text
    check (main_swatch in ('black', 'brown', 'red', 'golden', 'cream', 'white', 'gray')),
  add column sub_swatch text
    check (sub_swatch in ('black', 'brown', 'red', 'golden', 'cream', 'white', 'gray'));

-- ADR-22 컬럼 권한: 새 컬럼은 기본이 쓰기 불가라 FE 가 쓸 수 있게 연다.
grant insert (breed, main_swatch, sub_swatch) on pets to authenticated;
grant update (breed, main_swatch, sub_swatch) on pets to authenticated;
