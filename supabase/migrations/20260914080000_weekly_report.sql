-- ADR-011: 주간 리포트 집계는 SQL(합계)과 FastAPI(비교%·문구) 하이브리드로 나눈다.
-- daily_usage는 RLS로 "본인 select"만 이미 허용돼 있어서(20260910095500_rls_policies.sql),
-- 이 함수는 security definer가 아니라 기본값(invoker)으로 둔다 — RLS를 우회할 필요가
-- 없고, buy_item/complete_mission과 달리 쓰기가 아니라 읽기뿐이라 권한 상승이 불필요하다.
-- auth.uid()로 걸러서 인덱스(idx_daily_usage user_id)를 그대로 타게 한다.
-- https://app.notion.com/p/3db739629940816c9df6e2e8e5e9e393

create or replace function weekly_report()
returns table(week text, total_minutes int)
language sql
stable
as $$
  select
    case when usage_date < current_date - 7 then '지난주' else '이번주' end as week,
    coalesce(sum(minutes), 0)::int as total_minutes
  from daily_usage
  where user_id = auth.uid()
    and usage_date >= current_date - 14
    and usage_date < current_date
  group by 1
$$;

grant execute on function weekly_report() to authenticated;
