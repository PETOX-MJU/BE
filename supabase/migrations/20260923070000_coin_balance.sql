-- ADR-32: 홈 화면 코인 잔액. 잔액 = SUM(coin_ledger.amount)(ADR-004)인데 PostgREST
-- 집계가 꺼져 있어 FE가 원장 전체를 받아 합산해야 했다. 숫자 하나만 돌려준다.
--
-- invoker 권한이다. coin_ledger의 본인 행 select RLS가 이미 있어서 definer가 필요 없다.
-- where 절은 RLS와 겹치지만 idx_coin_ledger_user_id를 타게 하려고 명시한다.
create or replace function coin_balance()
returns int
language sql
stable
as $$
  select coalesce(sum(amount), 0)::int from coin_ledger where user_id = auth.uid()
$$;

revoke execute on function coin_balance() from public, anon;
grant execute on function coin_balance() to authenticated;
