-- ADR-004: 코인은 추가 전용 원장(coin_ledger). 잔액 = SUM(amount), 행은 삭제하지 않는다.
-- request_id는 멱등키 — 같은 요청이 재시도돼도 unique 제약이 중복 처리를 막는다.
-- 이 테이블에는 클라이언트용 INSERT 정책을 두지 않는다 — 오직 RPC(security definer 함수)만
-- 쓸 수 있어야 "코인 확인 없이 코인 지급"이 구조적으로 불가능해진다. (다음 마이그레이션)
-- https://app.notion.com/p/3d7739629940818eab12fe9fecf42db3

create table coin_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  pet_id uuid references pets(id) on delete set null,
  amount int not null,
  reason text not null,
  request_id uuid unique,
  created_at timestamptz not null default now()
);

create index idx_coin_ledger_user_id on coin_ledger(user_id);
create index idx_coin_ledger_pet_id on coin_ledger(pet_id);
