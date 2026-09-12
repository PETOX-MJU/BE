-- auth.users에 새 유저가 생기면 profiles 행을 자동으로 만든다.
-- FE가 가입 직후 insert를 깜빡해도 반쪽짜리 계정(goal_minutes 등이 없는)이 생기지 않는다.

create or replace function handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into profiles (id) values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function handle_new_user();
