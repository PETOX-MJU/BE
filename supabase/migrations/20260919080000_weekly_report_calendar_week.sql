-- ADR-23/24: 주간 리포트의 "주"를 어제까지 7일(롤링)에서 달력 주(월~일)로 바꾼다.
-- 대시보드 화면이 "9월 21일~27일"로 주를 표시하고 < > 로 이동하기 때문이다.
--
-- 오늘은 함수 안에서 KST로 정한다(daily_usage.usage_date가 클라이언트 기기 날짜라
-- DB 기본 타임존 UTC로 자르면 월요일 KST 0~9시에 주 경계가 어긋난다).
-- p_week_offset: 0=이번 주, -1=지난 주. 오늘(진행 중인 날)은 아직 덜 쌓였으므로
-- 집계에서 뺀다 — ADR-011부터 이어진 규칙.
--
-- 반환형과 인자가 바뀌어서 create or replace로는 못 바꾼다 — 기존 함수를 지우고 만든다.

drop function weekly_report();
drop function weekly_report_daily();
drop function weekly_report_by_app();

-- 합계: 선택한 주와 그 전 주를 "같은 일수"만큼만 비교한다. 진행 중인 주를 지난주
-- 7일 전체와 비교하면 월요일마다 "100% 줄였어요"가 나오기 때문이다. 끝난 주는 7일.
create function weekly_report(p_week_offset int default 0)
returns table(week text, total_minutes int, days_compared int)
language sql
stable
as $$
  with b as (
    select (now() at time zone 'Asia/Seoul')::date as today,
           date_trunc('week', now() at time zone 'Asia/Seoul')::date + p_week_offset * 7 as week_start
  ), n as (
    select week_start, greatest(0, least(7, today - week_start)) as days from b
  )
  select w.label, coalesce(sum(du.minutes), 0)::int, n.days
  from n
  cross join (values ('이번주', 0), ('지난주', -7)) as w(label, shift)
  left join daily_usage du
    on du.user_id = auth.uid()
    and du.usage_date >= n.week_start + w.shift
    and du.usage_date < n.week_start + w.shift + n.days
  group by w.label, n.days
$$;

grant execute on function weekly_report(int) to authenticated;

-- 일별: 선택한 주(이번주)와 그 전 주(지난주) 14일을 전부 만들고 왼쪽 조인한다.
-- 아직 끝나지 않은 날(오늘 이후)은 0이 아니라 NULL — "안 썼다"와 "아직 안 왔다"를
-- 그래프가 구분할 수 있어야 한다.
create function weekly_report_daily(p_week_offset int default 0)
returns table(week text, usage_date date, total_minutes int)
language sql
stable
as $$
  with b as (
    select (now() at time zone 'Asia/Seoul')::date as today,
           date_trunc('week', now() at time zone 'Asia/Seoul')::date + p_week_offset * 7 as week_start
  )
  select case when g >= 7 then '이번주' else '지난주' end,
         b.week_start - 7 + g,
         case when b.week_start - 7 + g < b.today then coalesce(sum(du.minutes), 0)::int end
  from b
  cross join generate_series(0, 13) as g
  left join daily_usage du
    on du.usage_date = b.week_start - 7 + g and du.user_id = auth.uid()
  group by b.today, b.week_start, g
  order by g
$$;

grant execute on function weekly_report_daily(int) to authenticated;

-- 앱별: 선택한 주에서 끝난 날만. 0분짜리 앱은 daily_usage에 행이 없어 자연히 빠진다.
create function weekly_report_by_app(p_week_offset int default 0)
returns table(app_name text, total_minutes int)
language sql
stable
as $$
  with b as (
    select (now() at time zone 'Asia/Seoul')::date as today,
           date_trunc('week', now() at time zone 'Asia/Seoul')::date + p_week_offset * 7 as week_start
  )
  select da.display_name, sum(du.minutes)::int
  from b
  join daily_usage du
    on du.user_id = auth.uid()
    and du.usage_date >= b.week_start
    and du.usage_date < least(b.week_start + 7, b.today)
  join detected_apps da on da.id = du.app_id
  group by da.display_name
  order by sum(du.minutes) desc
$$;

grant execute on function weekly_report_by_app(int) to authenticated;
