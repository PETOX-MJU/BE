-- ADR-33 후속: 카카오 가입은 raw_user_meta_data에 nickname 키가 없고 이름을
-- preferred_username·name 등에 넣는다(운영 카카오 가입 계정으로 확인). 그래서 카카오
-- 가입자의 profiles.nickname이 비었다. nickname이 없으면 카카오 프로필 이름을 쓴다.
create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into profiles (id, nickname)
  values (new.id, coalesce(
    nullif(trim(new.raw_user_meta_data->>'nickname'), ''),
    nullif(trim(new.raw_user_meta_data->>'preferred_username'), ''),
    nullif(trim(new.raw_user_meta_data->>'name'), '')
  ));
  return new;
end;
$$;

-- 트리거는 새 가입에만 적용되므로, 이미 가입해 닉네임이 빈 계정을 같은 규칙으로 한 번 채운다.
update profiles p
set nickname = coalesce(
  nullif(trim(u.raw_user_meta_data->>'nickname'), ''),
  nullif(trim(u.raw_user_meta_data->>'preferred_username'), ''),
  nullif(trim(u.raw_user_meta_data->>'name'), '')
)
from auth.users u
where u.id = p.id
  and p.nickname is null;
