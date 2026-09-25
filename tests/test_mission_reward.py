"""ADR-37: 폰이 판정한 미션에 코인을 주는 claim_mission_reward()를 검증한다.

서버는 성공 여부를 검증하지 못하므로, 조작 상한(날짜·종류당 1회, 7일·가입일 범위)이 핵심이다.
"""
import psycopg2
import pytest

from tests.conftest import as_admin, as_user, balance, requires_db

pytestmark = requires_db


def _claim(conn, user_id, kind, day_offset):
    """day_offset은 KST 오늘 기준(0=오늘, -1=어제)."""
    as_user(conn, user_id)
    try:
        cur = conn.cursor()
        cur.execute(
            "select claim_mission_reward(%s, (now() at time zone 'Asia/Seoul')::date + %s)",
            (kind, day_offset),
        )
        return cur.fetchone()[0]
    finally:
        as_admin(conn)


@pytest.fixture
def old_user(conn, user):
    """30일 전에 가입한 사용자. 가입일 하한에 걸리지 않게 한다."""
    conn.cursor().execute(
        "update profiles set created_at = now() - interval '30 days' where id = %s", (user,)
    )
    yield user


def test_pays_twenty_once_per_kind_and_date(conn, old_user):
    assert _claim(conn, old_user, "daily", -1) == 20
    assert _claim(conn, old_user, "daily", -1) == 0, "같은 날·종류 재호출은 지급하지 않는다"
    assert balance(conn, old_user) == 20


def test_daily_and_night_are_separate(conn, old_user):
    _claim(conn, old_user, "daily", -1)
    _claim(conn, old_user, "night", -1)
    _claim(conn, old_user, "daily", -2)
    assert balance(conn, old_user) == 60


@pytest.mark.parametrize("day_offset", [1, -8])
def test_rejects_future_and_older_than_seven_days(conn, old_user, day_offset):
    with pytest.raises(psycopg2.errors.RaiseException, match="mission date out of range"):
        _claim(conn, old_user, "daily", day_offset)
    assert balance(conn, old_user) == 0


def test_accepts_the_seven_day_boundary(conn, old_user):
    assert _claim(conn, old_user, "night", -7) == 20


def test_rejects_dates_before_signup(conn, user):
    """오늘 가입한 사용자는 어제 미션을 받을 수 없다."""
    with pytest.raises(psycopg2.errors.RaiseException, match="mission date out of range"):
        _claim(conn, user, "daily", -1)
    assert _claim(conn, user, "daily", 0) == 20


@pytest.mark.parametrize("kind", ["weekly", "DAILY", None])
def test_rejects_unknown_kind(conn, old_user, kind):
    with pytest.raises(psycopg2.errors.RaiseException, match="invalid mission kind"):
        _claim(conn, old_user, kind, -1)


def test_server_mission_schedules_are_off(conn):
    cur = conn.cursor()
    cur.execute(
        "select jobname from cron.job where jobname in "
        "('generate-daily-missions', 'settle-missions', 'send-mission-notifications')"
    )
    assert cur.fetchall() == []
