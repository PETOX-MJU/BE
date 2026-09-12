-- ADR-003: 사용시간은 세션이 아니라 일·앱별 집계로 저장한다.
-- 복합 PK가 "조합당 행 하나"를 보장해 클라의 upsert 동기화가 멱등하고,
-- 그 PK가 그대로 조회 인덱스가 된다. 세션 grain은 읽는 화면이 없어 저장하지 않는다.
-- https://app.notion.com/p/3d7739629940818f86e1d237d8d5f3ff

create table daily_usage (
  user_id uuid not null references auth.users(id) on delete cascade,
  app_id uuid not null references detected_apps(id),
  usage_date date not null,
  minutes int not null default 0,
  primary key (user_id, app_id, usage_date)
);
