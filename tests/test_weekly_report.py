"""ADR-011 weekly_report() SQL 함수를 로컬 Supabase에서 검증한다.

주장은 둘이다.
  1. 지난주(8~14일 전)와 이번주(0~7일 전) 합계가 정확히 나뉘어 계산된다
  2. security definer가 아니라 RLS(daily_usage own-select 정책)로 걸러지므로
     남의 데이터는 안 보인다 — buy_item/complete_mission과 다른 신뢰 모델이다

FastAPI 쪽(비교%·문구 생성) 테스트는 tests/test_weekly_report_api.py에서
get_weekly_report_rows를 dependency_overrides로 갈아끼워 별도로 본다.
"""
from datetime import date, timedelta

from tests.conftest import as_admin, as_user, requires_db

pytestmark = requires_db


def _app_id(conn):
    cur = conn.cursor()
    cur.execute("select id from detected_apps limit 1")
    return cur.fetchone()[0]


def _insert_usage(conn, user_id, app_id, days_ago, minutes):
    cur = conn.cursor()
    cur.execute(
        "insert into daily_usage (user_id, app_id, usage_date, minutes) "
        "values (%s, %s, %s, %s)",
        (user_id, app_id, date.today() - timedelta(days=days_ago), minutes),
    )
    cur.close()


def _call_weekly_report(conn):
    cur = conn.cursor()
    cur.execute("select week, total_minutes from weekly_report()")
    rows = cur.fetchall()
    cur.close()
    return dict(rows)


def test_weekly_report_splits_last_week_and_this_week(conn, user):
    app_id = _app_id(conn)
    # 이번주(0~6일 전)
    _insert_usage(conn, user, app_id, 1, 40)
    _insert_usage(conn, user, app_id, 3, 20)
    # 지난주(7~13일 전)
    _insert_usage(conn, user, app_id, 8, 60)
    _insert_usage(conn, user, app_id, 10, 25)
    conn.commit()

    as_user(conn, user)
    totals = _call_weekly_report(conn)
    as_admin(conn)

    assert totals.get("이번주", 0) == 60, "이번주 40+20이어야 한다"
    assert totals.get("지난주", 0) == 85, "지난주 60+25여야 한다"


def test_weekly_report_excludes_data_older_than_two_weeks(conn, user):
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, 20, 999)  # 2주보다 오래됨 — 안 잡혀야 함
    _insert_usage(conn, user, app_id, 1, 15)
    conn.commit()

    as_user(conn, user)
    totals = _call_weekly_report(conn)
    as_admin(conn)

    assert totals.get("이번주", 0) == 15
    assert "지난주" not in totals or totals["지난주"] == 0


def test_weekly_report_does_not_leak_other_users_data(conn, user, other_user):
    """security definer가 아니라 RLS로 걸러진다 — 남의 사용량은 0이어야 한다."""
    app_id = _app_id(conn)
    _insert_usage(conn, other_user, app_id, 1, 500)
    conn.commit()

    as_user(conn, user)
    totals = _call_weekly_report(conn)
    as_admin(conn)

    assert totals.get("이번주", 0) == 0, "다른 유저의 사용량이 섞이면 안 된다"


def test_weekly_report_with_no_data_returns_empty(conn, user):
    as_user(conn, user)
    totals = _call_weekly_report(conn)
    as_admin(conn)

    assert totals == {}


def test_weekly_report_seven_days_ago_counts_as_this_week(conn, user):
    """경계값: usage_date < current_date - 7 이므로 정확히 7일 전은 '이번주'에 들어간다."""
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, 7, 30)
    conn.commit()

    as_user(conn, user)
    totals = _call_weekly_report(conn)
    as_admin(conn)

    assert totals.get("이번주", 0) == 30
    assert "지난주" not in totals or totals["지난주"] == 0


def test_weekly_report_without_session_returns_no_rows(conn, user):
    """auth.uid()가 NULL이면(인증 안 된 호출) user_id = auth.uid() 조건이 항상
    거짓이라 아무 행도 안 나온다 — 에러도, 남의 데이터 노출도 아니라 빈 결과."""
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, 1, 40)
    conn.commit()

    as_admin(conn)  # role 리셋 + jwt.claims NULL -> auth.uid() = NULL
    totals = _call_weekly_report(conn)

    assert totals == {}


# --- 이슈 #16: weekly_report_daily() / weekly_report_by_app() ---


def _call_weekly_report_daily(conn):
    cur = conn.cursor()
    cur.execute("select usage_date, total_minutes from weekly_report_daily()")
    rows = cur.fetchall()
    cur.close()
    return {str(d): m for d, m in rows}


def _call_weekly_report_by_app(conn):
    cur = conn.cursor()
    cur.execute("select app_name, total_minutes from weekly_report_by_app()")
    rows = cur.fetchall()
    cur.close()
    return dict(rows)


def test_weekly_report_daily_fills_all_seven_days_including_zero(conn, user):
    """이번주(days_ago 1~7) 전부 7행이 나와야 그래프가 빈 날 없이 그려진다."""
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, 1, 40)
    _insert_usage(conn, user, app_id, 7, 15)
    conn.commit()

    as_user(conn, user)
    daily = _call_weekly_report_daily(conn)
    as_admin(conn)

    assert len(daily) == 7
    assert sum(daily.values()) == 55


def test_weekly_report_daily_excludes_today_and_last_week(conn, user):
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, 0, 999)  # 오늘 — 제외돼야 함
    _insert_usage(conn, user, app_id, 8, 999)  # 지난주 — 제외돼야 함
    conn.commit()

    as_user(conn, user)
    daily = _call_weekly_report_daily(conn)
    as_admin(conn)

    assert sum(daily.values()) == 0


def test_weekly_report_daily_does_not_leak_other_users_data(conn, user, other_user):
    app_id = _app_id(conn)
    _insert_usage(conn, other_user, app_id, 1, 500)
    conn.commit()

    as_user(conn, user)
    daily = _call_weekly_report_daily(conn)
    as_admin(conn)

    assert sum(daily.values()) == 0


def test_weekly_report_by_app_groups_and_excludes_unused_apps(conn, user):
    cur = conn.cursor()
    cur.execute("select id, display_name from detected_apps order by display_name limit 2")
    (app_a, name_a), (app_b, name_b) = cur.fetchall()

    _insert_usage(conn, user, app_a, 1, 30)
    _insert_usage(conn, user, app_a, 2, 20)  # 같은 앱, 합산돼야 함
    _insert_usage(conn, user, app_b, 8, 999)  # 지난주 — 제외돼야 함
    conn.commit()

    as_user(conn, user)
    by_app = _call_weekly_report_by_app(conn)
    as_admin(conn)

    assert by_app.get(name_a) == 50
    assert name_b not in by_app, "지난주에만 쓴 앱은 이번주 비중에 안 잡혀야 한다"


def test_weekly_report_by_app_does_not_leak_other_users_data(conn, user, other_user):
    app_id = _app_id(conn)
    _insert_usage(conn, other_user, app_id, 1, 500)
    conn.commit()

    as_user(conn, user)
    by_app = _call_weekly_report_by_app(conn)
    as_admin(conn)

    assert by_app == {}
