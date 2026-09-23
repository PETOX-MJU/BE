-- ADR-33(#30): 가입 시 닉네임을 profiles에 채운다. FE는 signUp의 options.data로
-- nickname을 보내는데, Confirm email이 켜져 있으면 가입 직후 세션이 없어 FE의
-- profiles update가 건너뛰어진다. 가입 트랜잭션 안에서 서버가 복사하면 설정과 무관하다.
--
-- 공백만 있거나 키가 없으면 null로 둔다(카카오 가입 등). 길이·중복 제약은 아직 없다.
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into profiles (id, nickname)
  values (new.id, nullif(trim(new.raw_user_meta_data->>'nickname'), ''));
  return new;
end;
$$;
