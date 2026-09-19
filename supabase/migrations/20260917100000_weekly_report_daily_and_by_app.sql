-- 이슈 #16: 대시보드 와이어프레임(3a)이 요구하는 일별 막대그래프·앱별 비중이
-- weekly_report()(ADR-011)엔 없었다 — 지난주/이번주 합계 2줄뿐이었다.
-- daily_usage가 이미 (user_id, app_id, usage_date, minutes)로 앱 단위까지
-- 저장하고 있어서 스키마 변경 없이 쿼리만 추가하면 된다.
--
-- "이번주" 범위는 weekly_report()와 반드시 같은 정의를 써야 한다 — 이 프로젝트가
-- 이미 정한 건 usage_date >= current_date - 7 and usage_date < current_date
-- (정확히 7일 전도 포함, 오늘은 미포함). 두 함수 다 이 범위를 그대로 쓴다.

-- 일별: 이번주 7일을 generate_series로 전부 만들고 왼쪽 조인한다 — 사용
-- 기록이 없는 날도 0분으로 빠짐없이 나와야 막대그래프가 7개를 다 그릴 수 있다.
create or replace function weekly_report_daily()
returns table(usage_date date, total_minutes int)
language sql
stable
as $$
  select d::date, coalesce(sum(du.minutes), 0)::int
  from generate_series(current_date - 7, current_date - 1, interval '1 day') as d
  left join daily_usage du
    on du.usage_date = d::date and du.user_id = auth.uid()
  group by d
  order by d
$$;

grant execute on function weekly_report_daily() to authenticated;

-- 앱별: 이번주 동안 실제로 쓴 앱만 나온다(0분짜리 앱은 애초에 daily_usage에
-- row가 없으므로 자연히 빠짐) — 프론트가 비중(%)을 계산할 때 그게 맞다.
create or replace function weekly_report_by_app()
returns table(app_name text, total_minutes int)
language sql
stable
as $$
  select da.display_name, sum(du.minutes)::int
  from daily_usage du
  join detected_apps da on da.id = du.app_id
  where du.user_id = auth.uid()
    and du.usage_date >= current_date - 7 and du.usage_date < current_date
  group by da.display_name
  order by sum(du.minutes) desc
$$;

grant execute on function weekly_report_by_app() to authenticated;
