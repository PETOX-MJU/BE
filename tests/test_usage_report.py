"""ADR-41: 폰 오버레이가 하루 누적값(숏폼 분, 펫 등장 횟수)을 최근 7일치씩 반복해서 올린다.

같은 날 값은 줄어들지 않아야 하고(앱 데이터 삭제·재설치로 기기 기록이 0부터 다시 시작해도),
펫 횟수는 report_pet_calls로 덮어쓰며, 범위 밖 날짜는 에러 없이 무시해야 한다
(FE는 에러가 나면 남은 날짜를 건너뛴다).
"""
import psycopg2
import pytest

from tests.conftest import as_admin, as_user, requires_db

pytestmark = requires_db


def _kst_date(conn, offset):
    cur = conn.cursor()
    cur.execute("select (now() at time zone 'Asia/Seoul')::date + %s", (offset,))
    return cur.fetchone()[0]


def _report(conn, user_id, day_offset, calls):
    as_user(conn, user_id)
    try:
        conn.cursor().execute(
            "select report_pet_calls(%s, %s)", (_kst_date(conn, day_offset), calls)
        )
    finally:
        as_admin(conn)


def _calls(conn, user_id, day_offset):
    cur = conn.cursor()
    cur.execute(
        "select calls from daily_pet_calls where user_id = %s and usage_date = %s",
        (user_id, _kst_date(conn, day_offset)),
    )
    row = cur.fetchone()
    return row[0] if row else None


@pytest.fixture
def old_user(conn, user):
    """30일 전 가입자. 가입일 하한에 걸리지 않게 한다."""
    conn.cursor().execute(
        "update profiles set created_at = now() - interval '30 days' where id = %s", (user,)
    )
    yield user


# ── report_pet_calls ────────────────────────────────────────────────────

def test_report_overwrites_with_daily_total_and_never_decreases(conn, old_user):
    _report(conn, old_user, -1, 3)
    _report(conn, old_user, -1, 5)
    assert _calls(conn, old_user, -1) == 5, "누적값을 다시 보내면 그 값으로 (더하지 않음)"
    _report(conn, old_user, -1, 0)
    assert _calls(conn, old_user, -1) == 5, "재설치로 0이 와도 줄지 않음"


@pytest.mark.parametrize("day_offset", [1, -8])
def test_report_ignores_future_and_older_than_seven_days(conn, old_user, day_offset):
    _report(conn, old_user, day_offset, 4)  # 에러가 나면 안 된다
    assert _calls(conn, old_user, day_offset) is None


def test_report_ignores_days_before_signup_without_error(conn, user):
    """오늘 가입자: FE가 오래된 날부터 7일치를 보내도 에러 없이 오늘 것만 들어간다."""
    for offset in range(-6, 1):
        _report(conn, user, offset, 2)
    assert _calls(conn, user, -1) is None
    assert _calls(conn, user, 0) == 2


def test_report_ignores_negative_calls(conn, old_user):
    _report(conn, old_user, 0, -3)
    assert _calls(conn, old_user, 0) is None


def test_anon_cannot_report(conn):
    cur = conn.cursor()
    cur.execute("set role anon")
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("select report_pet_calls(current_date, 1)")
    finally:
        conn.cursor().execute("reset role")


# ── daily_usage 는 줄지 않는다 ──────────────────────────────────────────

def test_usage_upsert_keeps_the_larger_minutes(conn, user):
    cur = conn.cursor()
    cur.execute("select id from detected_apps order by package_name limit 1")
    app_id = cur.fetchone()[0]
    as_user(conn, user)
    try:
        for minutes in (40, 10):
            conn.cursor().execute(
                "insert into daily_usage (user_id, app_id, usage_date, minutes) "
                "values (%s, %s, (now() at time zone 'Asia/Seoul')::date, %s) "
                "on conflict (user_id, app_id, usage_date) do update set minutes = excluded.minutes",
                (user, app_id, minutes),
            )
    finally:
        as_admin(conn)
    cur.execute(
        "select minutes from daily_usage where user_id = %s and app_id = %s", (user, app_id)
    )
    assert cur.fetchone()[0] == 40


# ── 보고한 펫 횟수로 미션이 판정된다 ─────────────────────────────────────

@pytest.mark.parametrize("calls, expected", [(2, "completed"), (3, "failed")])
def test_pet_call_mission_settles_on_reported_count(conn, old_user, calls, expected):
    conn.cursor().execute("select generate_daily_missions()")
    conn.cursor().execute(
        "update missions set valid_date = valid_date - 1 where id in "
        "(select mission_id from user_missions where user_id = %s)",
        (old_user,),
    )
    # 어제 사용시간 보고(0분)가 있어야 판정한다 (require_usage_sync)
    conn.cursor().execute(
        "insert into daily_usage (user_id, app_id, usage_date, minutes) "
        "select %s, id, (now() at time zone 'Asia/Seoul')::date - 1, 0 "
        "from detected_apps order by package_name limit 1",
        (old_user,),
    )
    _report(conn, old_user, -1, calls)  # 목표는 최소 2회

    conn.cursor().execute("select settle_missions()")

    cur = conn.cursor()
    cur.execute(
        "select um.status from user_missions um join missions m on m.id = um.mission_id "
        "where um.user_id = %s and m.metric = 'pet_calls'",
        (old_user,),
    )
    assert cur.fetchone()[0] == expected

