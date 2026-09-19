"""ADR-25/26: 미션 수령 검증, 자동 정산, 앱별 미션 생성을 로컬 Supabase에서 검증한다.

이전에는 complete_mission이 사용시간을 전혀 보지 않아 미션 생성 직후 호출해도 코인이
나갔고, failed 상태를 만드는 곳도 없었다. 여기서는
  1. 하루가 끝나기 전이나 목표를 넘겼으면 수령이 거부된다
  2. 수령하지 않은 미션은 정산 때 지켰으면 같은 코인, 못 지켰으면 failed가 되고
     재실행해도 이중 지급이 없다
  3. 오늘 미션은 앱별 2개 + 펫 호출 1개로 생성된다
를 본다. 날짜는 전부 DB의 KST 기준이다.
"""
import uuid

import psycopg2
import pytest

from tests.conftest import _make_mission, as_admin, as_user, balance, requires_db

pytestmark = requires_db


def _apps(conn, n=3):
    cur = conn.cursor()
    cur.execute("select id, display_name from detected_apps order by display_name limit %s", (n,))
    rows = cur.fetchall()
    cur.close()
    return rows


def _usage(conn, user_id, app_id, day_offset, minutes):
    cur = conn.cursor()
    cur.execute(
        "insert into daily_usage (user_id, app_id, usage_date, minutes) "
        "values (%s, %s, (now() at time zone 'Asia/Seoul')::date + %s, %s)",
        (user_id, app_id, day_offset, minutes),
    )
    cur.close()


def _pet_calls(conn, user_id, day_offset, calls):
    cur = conn.cursor()
    cur.execute(
        "insert into daily_pet_calls (user_id, usage_date, calls) "
        "values (%s, (now() at time zone 'Asia/Seoul')::date + %s, %s)",
        (user_id, day_offset, calls),
    )
    cur.close()


def _typed_mission(conn, user_id, *, metric, app_id=None, target, day_offset=-1):
    """앱 지정 또는 펫 호출 미션. 보상 50코인."""
    mid, umid = str(uuid.uuid4()), str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "insert into missions (id, type, title, target_minutes, target_count, reward_coins, "
        "valid_date, app_id, metric) values (%s, 'daily', 't', %s, %s, 50, "
        "(now() at time zone 'Asia/Seoul')::date + %s, %s, %s)",
        (
            mid,
            target if metric == "usage_minutes" else None,
            target if metric == "pet_calls" else None,
            day_offset,
            app_id,
            metric,
        ),
    )
    cur.execute(
        "insert into user_missions (id, user_id, mission_id) values (%s, %s, %s)",
        (umid, user_id, mid),
    )
    cur.close()
    return umid


def _claim(conn, user_id, um_id, request_id=None):
    as_user(conn, user_id)
    try:
        conn.cursor().execute(
            "select complete_mission(%s, %s)", (um_id, request_id or str(uuid.uuid4()))
        )
    finally:
        as_admin(conn)


def _status(conn, um_id):
    cur = conn.cursor()
    cur.execute("select status from user_missions where id = %s", (um_id,))
    return cur.fetchone()[0]


# ── 수령(complete_mission) ───────────────────────────────────────────────

def test_claim_before_the_day_ends_is_rejected(conn, user, user_mission):
    """오늘 미션은 하루가 끝나기 전엔 수령할 수 없다 — 생성 직후 코인 지급 구멍."""
    with pytest.raises(psycopg2.errors.RaiseException, match="not finished"):
        _claim(conn, user, user_mission)
    assert balance(conn, user) == 0
    assert _status(conn, user_mission) == "in_progress"


def test_claim_after_the_day_pays_once_even_if_retried(conn, user, finished_mission):
    req = str(uuid.uuid4())
    _claim(conn, user, finished_mission, req)
    _claim(conn, user, finished_mission, req)  # 같은 request_id 재시도

    assert balance(conn, user) == 50
    assert _status(conn, finished_mission) == "completed"


def test_claim_is_rejected_when_the_target_was_exceeded(conn, user):
    app_id, _ = _apps(conn)[0]
    um = _typed_mission(conn, user, metric="usage_minutes", app_id=app_id, target=30)
    _usage(conn, user, app_id, -1, 31)

    with pytest.raises(psycopg2.errors.RaiseException, match="target not met"):
        _claim(conn, user, um)
    assert balance(conn, user) == 0


def test_app_mission_counts_only_that_apps_usage(conn, user):
    (app_a, _), (app_b, _) = _apps(conn)[:2]
    um = _typed_mission(conn, user, metric="usage_minutes", app_id=app_a, target=30)
    _usage(conn, user, app_b, -1, 999)  # 다른 앱의 사용은 세지 않는다
    _usage(conn, user, app_a, -1, 30)  # 정확히 목표 = 이하이므로 성공

    _claim(conn, user, um)
    assert balance(conn, user) == 50


def test_pet_calls_mission_uses_the_call_count(conn, user):
    um = _typed_mission(conn, user, metric="pet_calls", target=2)
    _pet_calls(conn, user, -1, 3)

    with pytest.raises(psycopg2.errors.RaiseException, match="target not met"):
        _claim(conn, user, um)


# ── 자동 정산(settle_missions) ───────────────────────────────────────────

def _settle(conn):
    conn.cursor().execute("select settle_missions()")


def test_settle_pays_achieved_and_fails_missed_and_ignores_today(conn, user):
    app_id, _ = _apps(conn)[0]
    achieved = _typed_mission(conn, user, metric="usage_minutes", app_id=app_id, target=30)
    missed = _typed_mission(conn, user, metric="pet_calls", target=2)
    _pet_calls(conn, user, -1, 9)
    today = _make_mission(conn, user, 0)

    _settle(conn)

    assert _status(conn, achieved) == "completed"
    assert _status(conn, missed) == "failed"
    assert _status(conn, today) == "in_progress", "오늘 미션은 아직 안 끝났다"
    assert balance(conn, user) == 50, "지킨 한 건만 지급"


def test_settle_twice_does_not_pay_twice(conn, user, finished_mission):
    _settle(conn)
    _settle(conn)
    assert balance(conn, user) == 50


def test_settle_does_not_pay_a_mission_that_was_already_claimed(conn, user, finished_mission):
    _claim(conn, user, finished_mission)
    _settle(conn)
    assert balance(conn, user) == 50, "수령 50 + 정산 0이어야 한다"


def test_client_cannot_call_settle_or_the_achievement_check(conn, user, finished_mission):
    as_user(conn, user)
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            conn.cursor().execute("select settle_missions()")
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            conn.cursor().execute(
                "select mission_achieved(%s, %s)", (user, str(uuid.uuid4()))
            )
    finally:
        as_admin(conn)


# ── 미션 생성 ────────────────────────────────────────────────────────────

def _enable(conn, user_id, app_id, enabled=True):
    conn.cursor().execute(
        "insert into user_detected_apps (user_id, app_id, is_enabled) values (%s, %s, %s)",
        (user_id, app_id, enabled),
    )


def _todays_missions(conn, user_id):
    cur = conn.cursor()
    cur.execute(
        "select m.metric, m.app_id, m.target_minutes, m.target_count, m.reward_coins "
        "from user_missions um join missions m on m.id = um.mission_id "
        "where um.user_id = %s and m.type = 'daily' "
        "and m.valid_date = (now() at time zone 'Asia/Seoul')::date",
        (user_id,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def test_generates_top_two_apps_plus_pet_calls(conn, user):
    (a, _), (b, _), (c, _) = _apps(conn)
    for app in (a, b, c):
        _enable(conn, user, app)
    _usage(conn, user, a, -1, 100)
    _usage(conn, user, b, -1, 5)
    _usage(conn, user, c, -1, 60)
    _pet_calls(conn, user, -1, 6)

    conn.cursor().execute("select generate_daily_missions()")
    missions = _todays_missions(conn, user)

    by_app = {m[1]: m for m in missions if m[0] == "usage_minutes"}
    assert set(by_app) == {a, c}, "어제 사용량 상위 2개 앱만 (b 제외)"
    assert by_app[a][2] == 90 and by_app[c][2] == 50, "어제 사용량 - 10분"
    pet = [m for m in missions if m[0] == "pet_calls"]
    assert len(pet) == 1 and pet[0][3] == 5, "어제 횟수 - 1"
    assert len(missions) == 3 and all(m[4] == 20 for m in missions)


def test_generation_floors_targets_and_skips_disabled_apps(conn, user):
    (a, _), (b, _) = _apps(conn)[:2]
    _enable(conn, user, a)
    _enable(conn, user, b, enabled=False)
    _usage(conn, user, a, -1, 5)  # 5 - 10 < 15 이므로 최소 15분
    _usage(conn, user, b, -1, 999)  # 꺼둔 앱은 미션이 안 생긴다

    conn.cursor().execute("select generate_daily_missions()")
    missions = _todays_missions(conn, user)

    apps = [m for m in missions if m[0] == "usage_minutes"]
    assert [(m[1], m[2]) for m in apps] == [(a, 15)]
    assert [m[3] for m in missions if m[0] == "pet_calls"] == [2], "횟수도 최소 2회"


def test_generation_is_idempotent(conn, user):
    (a, _) = _apps(conn)[0]
    _enable(conn, user, a)
    conn.cursor().execute("select generate_daily_missions()")
    conn.cursor().execute("select generate_daily_missions()")
    assert len(_todays_missions(conn, user)) == 2


# ── 펫 호출 횟수 RLS ─────────────────────────────────────────────────────

def test_pet_calls_are_private_to_their_owner(conn, user, other_user):
    _pet_calls(conn, other_user, -1, 4)

    as_user(conn, user)
    try:
        cur = conn.cursor()
        cur.execute("select count(*) from daily_pet_calls")
        assert cur.fetchone()[0] == 0, "남의 횟수는 안 보인다"
        cur.execute(
            "insert into daily_pet_calls (user_id, usage_date, calls) values (%s, current_date, 1)",
            (user,),
        )
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(
                "insert into daily_pet_calls (user_id, usage_date, calls) "
                "values (%s, current_date, 1)",
                (other_user,),
            )
    finally:
        as_admin(conn)
