"""ADR-011/23/24 weekly_report*() SQL 함수를 로컬 Supabase에서 검증한다.

주장은 셋이다.
  1. "주"는 KST 달력 주(월~일)이고 p_week_offset으로 이동한다 (0=이번 주, -1=지난 주)
  2. 오늘(진행 중인 날)은 집계에서 빠지고, 진행 중인 주는 지난주와 같은 일수만 비교한다
  3. security definer가 아니라 RLS(daily_usage own-select 정책)로 걸러지므로
     남의 데이터는 안 보인다 — buy_item/complete_mission과 다른 신뢰 모델이다

오늘은 DB의 KST 값으로 계산해서 테스트가 실행 요일에 상관없이 같은 뜻을 갖는다.

FastAPI 쪽(비교%·문구 생성) 테스트는 tests/test_weekly_report_api.py에서
get_weekly_report_rows를 dependency_overrides로 갈아끼워 별도로 본다.
"""
from datetime import timedelta

from tests.conftest import as_admin, as_user, requires_db

pytestmark = requires_db


def _kst_today(conn):
    cur = conn.cursor()
    cur.execute("select (now() at time zone 'Asia/Seoul')::date")
    return cur.fetchone()[0]


def _week_start(conn, offset=0):
    today = _kst_today(conn)
    return today - timedelta(days=today.weekday()) + timedelta(days=7 * offset)


def _app_id(conn):
    cur = conn.cursor()
    cur.execute("select id from detected_apps limit 1")
    return cur.fetchone()[0]


def _insert_usage(conn, user_id, app_id, usage_date, minutes):
    cur = conn.cursor()
    cur.execute(
        "insert into daily_usage (user_id, app_id, usage_date, minutes) "
        "values (%s, %s, %s, %s)",
        (user_id, app_id, usage_date, minutes),
    )
    cur.close()


def _call_weekly_report(conn, offset=0):
    cur = conn.cursor()
    cur.execute(
        "select week, total_minutes, days_compared from weekly_report(%s)", (offset,)
    )
    rows = cur.fetchall()
    cur.close()
    return {w: m for w, m, _ in rows}, ({d for _, _, d in rows} or {None})


def test_weekly_report_splits_selected_week_and_previous_week(conn, user):
    app_id = _app_id(conn)
    this_start, last_start = _week_start(conn, -1), _week_start(conn, -2)
    _insert_usage(conn, user, app_id, this_start + timedelta(days=1), 40)
    _insert_usage(conn, user, app_id, this_start + timedelta(days=3), 20)
    _insert_usage(conn, user, app_id, last_start + timedelta(days=2), 60)
    _insert_usage(conn, user, app_id, last_start + timedelta(days=5), 25)

    as_user(conn, user)
    totals, days = _call_weekly_report(conn, -1)
    as_admin(conn)

    assert totals == {"이번주": 60, "지난주": 85}
    assert days == {7}, "끝난 주는 7일 전부 비교한다"


def test_weekly_report_week_boundary_is_monday(conn, user):
    """월요일은 그 주, 그 전 일요일은 전 주에 들어간다."""
    app_id = _app_id(conn)
    start = _week_start(conn, -1)
    _insert_usage(conn, user, app_id, start, 30)
    _insert_usage(conn, user, app_id, start - timedelta(days=1), 20)

    as_user(conn, user)
    totals, _ = _call_weekly_report(conn, -1)
    as_admin(conn)

    assert totals == {"이번주": 30, "지난주": 20}


def test_weekly_report_excludes_older_than_previous_week(conn, user):
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, _week_start(conn, -3) + timedelta(days=6), 999)

    as_user(conn, user)
    totals, _ = _call_weekly_report(conn, -1)
    as_admin(conn)

    assert totals == {"이번주": 0, "지난주": 0}


def test_current_week_compares_same_number_of_days_and_excludes_today(conn, user):
    """진행 중인 주는 지난주 7일 전체가 아니라 같은 일수(끝난 날)만 비교한다."""
    app_id = _app_id(conn)
    today = _kst_today(conn)
    this_start, last_start = _week_start(conn, 0), _week_start(conn, -1)
    days = (today - this_start).days  # 월요일이면 0

    for i in range(7):
        _insert_usage(conn, user, app_id, last_start + timedelta(days=i), 10)
    for i in range(days):
        _insert_usage(conn, user, app_id, this_start + timedelta(days=i), 5)
    _insert_usage(conn, user, app_id, today, 777)  # 오늘 — 제외돼야 함

    as_user(conn, user)
    totals, compared = _call_weekly_report(conn, 0)
    as_admin(conn)

    assert compared == {days}
    assert totals == {"이번주": 5 * days, "지난주": 10 * days}


def test_weekly_report_does_not_leak_other_users_data(conn, user, other_user):
    """security definer가 아니라 RLS로 걸러진다 — 남의 사용량은 0이어야 한다."""
    app_id = _app_id(conn)
    _insert_usage(conn, other_user, app_id, _week_start(conn, -1) + timedelta(days=1), 500)

    as_user(conn, user)
    totals, _ = _call_weekly_report(conn, -1)
    as_admin(conn)

    assert totals["이번주"] == 0, "다른 유저의 사용량이 섞이면 안 된다"


def test_weekly_report_with_no_data_returns_zero_for_both_weeks(conn, user):
    as_user(conn, user)
    totals, _ = _call_weekly_report(conn, -1)
    as_admin(conn)

    assert totals == {"이번주": 0, "지난주": 0}


def test_weekly_report_without_session_returns_zeros(conn, user):
    """auth.uid()가 NULL이면(인증 안 된 호출) user_id = auth.uid() 조건이 항상
    거짓이라 남의 데이터 노출 없이 0만 나온다."""
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, _week_start(conn, -1) + timedelta(days=1), 40)

    as_admin(conn)  # role 리셋 + jwt.claims NULL -> auth.uid() = NULL
    totals, _ = _call_weekly_report(conn, -1)

    assert totals == {"이번주": 0, "지난주": 0}


# --- weekly_report_daily() / weekly_report_by_app() ---


def _call_weekly_report_daily(conn, offset=0):
    cur = conn.cursor()
    cur.execute(
        "select week, usage_date, total_minutes from weekly_report_daily(%s)", (offset,)
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def _call_weekly_report_by_app(conn, offset=0):
    cur = conn.cursor()
    cur.execute("select app_name, total_minutes from weekly_report_by_app(%s)", (offset,))
    rows = cur.fetchall()
    cur.close()
    return dict(rows)


def test_daily_returns_fourteen_consecutive_days_starting_monday(conn, user):
    """선택한 주 + 전 주 14일이 월요일부터 빈 날 없이 나와야 겹침 그래프가 그려진다."""
    as_user(conn, user)
    rows = _call_weekly_report_daily(conn, -1)
    as_admin(conn)

    dates = [d for _, d, _ in rows]
    assert len(rows) == 14
    assert dates[0] == _week_start(conn, -2)
    assert dates[0].weekday() == 0
    assert all(b - a == timedelta(days=1) for a, b in zip(dates, dates[1:]))
    assert [w for w, _, _ in rows] == ["지난주"] * 7 + ["이번주"] * 7


def test_daily_fills_zero_for_finished_days_and_sums_usage(conn, user):
    app_id = _app_id(conn)
    start = _week_start(conn, -1)
    _insert_usage(conn, user, app_id, start + timedelta(days=1), 40)
    _insert_usage(conn, user, app_id, start + timedelta(days=6), 15)

    as_user(conn, user)
    rows = _call_weekly_report_daily(conn, -1)
    as_admin(conn)

    minutes = {d: m for _, d, m in rows}
    assert all(m is not None for m in minutes.values()), "끝난 주는 전부 숫자"
    assert minutes[start + timedelta(days=1)] == 40
    assert minutes[start + timedelta(days=6)] == 15
    assert sum(m for d, m in minutes.items() if d >= start) == 55


def test_daily_marks_unfinished_days_null_not_zero(conn, user):
    """오늘과 미래는 0이 아니라 NULL — '안 썼다'와 '아직 안 왔다'를 구분한다."""
    app_id = _app_id(conn)
    today = _kst_today(conn)
    _insert_usage(conn, user, app_id, today, 999)  # 오늘 — 제외돼야 함

    as_user(conn, user)
    rows = _call_weekly_report_daily(conn, 0)
    as_admin(conn)

    for _, d, m in rows:
        assert (m is None) == (d >= today), f"{d}: {m}"


def test_positive_offset_is_clamped_to_this_week(conn, user):
    """미래 주는 데이터가 있을 수 없다 — SQL이 직접 호출돼도 이번 주로 붙인다.

    FastAPI의 Query(le=0)는 /reports/weekly 경로에만 걸리므로, PostgREST로
    직접 부르는 경우까지 막으려면 함수 안에서 클램프해야 한다.
    """
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, _week_start(conn, -1) + timedelta(days=1), 35)

    as_user(conn, user)
    this_week = _call_weekly_report_daily(conn, 0)
    clamped = _call_weekly_report_daily(conn, 3)
    totals_this, _ = _call_weekly_report(conn, 0)
    totals_clamped, _ = _call_weekly_report(conn, 3)
    by_app_this = _call_weekly_report_by_app(conn, 0)
    by_app_clamped = _call_weekly_report_by_app(conn, 3)
    as_admin(conn)

    assert clamped == this_week
    assert totals_clamped == totals_this
    assert by_app_clamped == by_app_this


def test_daily_does_not_leak_other_users_data(conn, user, other_user):
    app_id = _app_id(conn)
    _insert_usage(conn, other_user, app_id, _week_start(conn, -1) + timedelta(days=1), 500)

    as_user(conn, user)
    rows = _call_weekly_report_daily(conn, -1)
    as_admin(conn)

    assert sum(m or 0 for _, _, m in rows) == 0


def test_by_app_groups_and_excludes_unused_apps_and_other_weeks(conn, user):
    cur = conn.cursor()
    cur.execute("select id, display_name from detected_apps order by display_name limit 2")
    (app_a, name_a), (app_b, name_b) = cur.fetchall()
    start = _week_start(conn, -1)

    _insert_usage(conn, user, app_a, start + timedelta(days=1), 30)
    _insert_usage(conn, user, app_a, start + timedelta(days=2), 20)  # 같은 앱, 합산
    _insert_usage(conn, user, app_b, start - timedelta(days=1), 999)  # 전 주 — 제외

    as_user(conn, user)
    by_app = _call_weekly_report_by_app(conn, -1)
    as_admin(conn)

    assert by_app == {name_a: 50}


def test_by_app_excludes_today(conn, user):
    app_id = _app_id(conn)
    _insert_usage(conn, user, app_id, _kst_today(conn), 999)

    as_user(conn, user)
    by_app = _call_weekly_report_by_app(conn, 0)
    as_admin(conn)

    assert by_app == {}


def test_by_app_does_not_leak_other_users_data(conn, user, other_user):
    app_id = _app_id(conn)
    _insert_usage(conn, other_user, app_id, _week_start(conn, -1) + timedelta(days=1), 500)

    as_user(conn, user)
    by_app = _call_weekly_report_by_app(conn, -1)
    as_admin(conn)

    assert by_app == {}
