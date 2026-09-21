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

from tests.conftest import (
    _make_mission,
    as_admin,
    as_user,
    balance,
    requires_db,
    sync_heartbeat,
)

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
    sync_heartbeat(conn, user, -1)
    _pet_calls(conn, user, -1, 3)

    with pytest.raises(psycopg2.errors.RaiseException, match="target not met"):
        _claim(conn, user, um)


# ── 자동 정산(settle_missions) ───────────────────────────────────────────

def _settle(conn):
    conn.cursor().execute("select settle_missions()")


def test_settle_pays_achieved_and_fails_missed_and_ignores_today(conn, user):
    """방금 끝난 하루(어제)를 판정한다 — 날짜가 바뀌는 시점에 도는 자동 정산이다."""
    app_id, _ = _apps(conn)[0]
    achieved = _typed_mission(
        conn, user, metric="usage_minutes", app_id=app_id, target=30, day_offset=-1
    )
    missed = _typed_mission(conn, user, metric="pet_calls", target=2, day_offset=-1)
    sync_heartbeat(conn, user, -1)
    _pet_calls(conn, user, -1, 9)
    today = _make_mission(conn, user, 0)

    _settle(conn)

    assert _status(conn, achieved) == "completed"
    assert _status(conn, missed) == "failed"
    assert _status(conn, today) == "in_progress", "오늘 미션은 아직 안 끝났다"
    assert balance(conn, user) == 50, "지킨 한 건만 지급"


def test_settle_does_not_pay_when_usage_was_never_synced(conn, user):
    """수집 기록이 없는 날은 지급하지 않는다.

    mission_achieved가 coalesce(..., 0)을 쓰기 때문에, 이 전제가 없으면 사용시간이
    한 번도 안 올라온 날도 0분으로 읽혀 0 <= target이 참이 된다. FE에 수집이 붙기
    전까지는 그게 "아무것도 안 해도 매일 전부 성공"을 뜻한다.
    """
    app_id, _ = _apps(conn)[0]
    usage = _typed_mission(
        conn, user, metric="usage_minutes", app_id=app_id, target=30, day_offset=-1
    )
    pet = _typed_mission(conn, user, metric="pet_calls", target=2, day_offset=-1)
    # daily_usage 행을 심지 않는다 — 앱이 그날 한 번도 보고하지 않은 상태

    _settle(conn)

    assert [_status(conn, usage), _status(conn, pet)] == ["failed", "failed"]
    assert balance(conn, user) == 0


def test_a_zero_minute_row_is_enough_to_be_judged(conn, user):
    """0분짜리 행이라도 있으면 정상 판정한다.

    전제는 "많이 썼는가"가 아니라 "그날 앱이 살아서 보고했는가"다. 폰을 켜고
    숏폼 앱을 하나도 안 썼다면 0분이 올라오고, 그건 성공이 맞다.
    """
    usage = _typed_mission(conn, user, metric="usage_minutes", target=30, day_offset=-1)
    pet = _typed_mission(conn, user, metric="pet_calls", target=2, day_offset=-1)
    sync_heartbeat(conn, user, -1)

    _settle(conn)

    assert [_status(conn, usage), _status(conn, pet)] == ["completed", "completed"]
    assert balance(conn, user) == 100, "둘 다 50코인씩"


def test_settle_fails_stale_missions_without_paying(conn, user):
    """하루가 끝난 지 이틀 넘은 미션은 지급 없이 failed로 정리한다.

    mission_achieved는 기록이 없으면 "지켰다"로 보는데, 오래된 미션은 그 기록이
    없는 게 정상이다. 하한이 없으면 배포 직후 첫 실행에서 그동안 쌓인 미수령
    미션이 전부 성공 판정으로 한꺼번에 지급된다.
    """
    stale = [
        _typed_mission(conn, user, metric="usage_minutes", target=30, day_offset=d)
        for d in (-2, -10, -40)
    ]

    _settle(conn)

    assert [_status(conn, um) for um in stale] == ["failed"] * 3
    assert balance(conn, user) == 0, "오래된 미션은 한 푼도 지급하지 않는다"


def test_settle_twice_does_not_pay_twice(conn, user, finished_mission):
    _settle(conn)
    _settle(conn)
    assert balance(conn, user) == 50


def test_settle_does_not_pay_a_mission_that_was_already_claimed(conn, user, finished_mission):
    _claim(conn, user, finished_mission)
    _settle(conn)
    assert balance(conn, user) == 50, "수령 50 + 정산 0이어야 한다"


def test_claiming_an_already_settled_mission_is_a_no_op(conn, user, finished_mission):
    """정산이 먼저 지급한 뒤 FE가 "받기"를 눌러도 에러가 아니라 조용히 끝나야 한다.

    날짜가 바뀌는 시점에 정산하면 수령 가능한 시간이 사실상 없다(수령 조건인
    valid_date < 오늘이 참이 되는 순간이 곧 정산 시각이다). 그래서 "받기"는 거의
    항상 이 경로로 들어온다. 코인은 이미 들어가 있는데 예외가 나면 "성공했는데
    에러 화면"이 된다.
    """
    _settle(conn)
    assert _status(conn, finished_mission) == "completed"
    assert balance(conn, user) == 50

    _claim(conn, user, finished_mission)  # 예외가 나면 안 된다

    assert balance(conn, user) == 50, "두 번 지급되면 안 된다"


def test_claiming_a_weekly_mission_says_so_instead_of_not_found(conn, user):
    """weekly 미션은 아직 판정할 수 없다 — 그 사실을 조용히 삼키지 않는다.

    예전에는 select 조건에 type = 'daily'가 있어서 'mission not found'가 났다.
    미션이 실제로 있는데 없다고 말하는 셈이라 FR-070을 넣을 때 원인을 찾기 어렵다.
    """
    mid, umid = str(uuid.uuid4()), str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "insert into missions (id, type, title, target_minutes, reward_coins, valid_date) "
        "values (%s, 'weekly', '주간', 300, 100, "
        "(now() at time zone 'Asia/Seoul')::date - 1)",
        (mid,),
    )
    cur.execute(
        "insert into user_missions (id, user_id, mission_id) values (%s, %s, %s)",
        (umid, user, mid),
    )
    cur.close()

    with pytest.raises(psycopg2.errors.RaiseException, match="only daily missions"):
        _claim(conn, user, umid)
    assert balance(conn, user) == 0


def test_claiming_a_failed_mission_still_raises(conn, user):
    um = _typed_mission(conn, user, metric="pet_calls", target=2, day_offset=-1)
    sync_heartbeat(conn, user, -1)  # 미동기화가 아니라 목표 초과로 실패시킨다
    _pet_calls(conn, user, -1, 9)
    _settle(conn)
    assert _status(conn, um) == "failed"

    with pytest.raises(psycopg2.errors.RaiseException, match="already completed"):
        _claim(conn, user, um)
    assert balance(conn, user) == 0


def test_client_cannot_call_the_batches_or_the_achievement_check(conn, user):
    """전체 유저의 코인·미션을 움직이는 배치는 로그인 사용자가 부를 수 없어야 한다.

    generate_daily_missions는 create or replace로 다시 써도 최초 create 때
    PUBLIC에 부여된 execute가 남아 있어서, 명시적으로 회수해야 막힌다.
    """
    for sql, params in (
        ("select settle_missions()", ()),
        ("select generate_daily_missions()", ()),
        ("select mission_achieved(%s, %s)", (user, str(uuid.uuid4()))),
    ):
        as_user(conn, user)
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                conn.cursor().execute(sql, params)
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


def test_generation_falls_back_to_total_usage_when_no_apps_are_enabled(conn, user):
    """활성 앱이 없으면 펫 호출 미션 하나만 남는데, 그 미션은 기록이 없을 때 항상
    성공이라 매일 코인이 공짜로 나간다. 전체 사용시간 미션으로 폴백해야 한다.

    user_detected_apps를 채우는 경로가 BE에 없어서(FE 온보딩이 맡는다) 실제로
    비어 있을 수 있다.
    """
    app_id, _ = _apps(conn)[0]
    _usage(conn, user, app_id, -1, 100)  # 앱은 안 켰지만 사용 기록은 있다

    conn.cursor().execute("select generate_daily_missions()")
    missions = _todays_missions(conn, user)

    usage_missions = [m for m in missions if m[0] == "usage_minutes"]
    assert len(usage_missions) == 1
    assert usage_missions[0][1] is None, "앱 지정 없는 전체 사용시간 미션이어야 한다"
    assert usage_missions[0][2] == 90, "어제 총 사용시간 - 10분"
    assert len(missions) == 2, "폴백 1개 + 펫 호출 1개"


# ── 펫 호출 횟수 ─────────────────────────────────────────────────────────

def _call_count(conn, user_id):
    cur = conn.cursor()
    cur.execute(
        "select calls from daily_pet_calls "
        "where user_id = %s and usage_date = (now() at time zone 'Asia/Seoul')::date",
        (user_id,),
    )
    row = cur.fetchone()
    return row[0] if row else None


def test_pet_calls_are_private_and_not_client_writable(conn, user, other_user):
    """calls가 곧 미션 성공 판정이라 클라이언트가 직접 쓰면 0으로 적어 코인을 가져간다.

    #22가 pets.affection·profiles.pet_slot_limit에 대해 막은 것과 같은 이유로,
    select만 열고 쓰기는 record_pet_call()에만 맡긴다.
    """
    _pet_calls(conn, other_user, -1, 4)

    as_user(conn, user)
    try:
        cur = conn.cursor()
        cur.execute("select count(*) from daily_pet_calls")
        assert cur.fetchone()[0] == 0, "남의 횟수는 안 보인다"
    finally:
        as_admin(conn)

    for target in (user, other_user):
        as_user(conn, user)
        try:
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                conn.cursor().execute(
                    "insert into daily_pet_calls (user_id, usage_date, calls) "
                    "values (%s, current_date, 0)",
                    (target,),
                )
        finally:
            as_admin(conn)


def test_record_pet_call_counts_up_for_the_caller_only(conn, user, other_user):
    _pet_calls(conn, other_user, 0, 7)

    as_user(conn, user)
    try:
        cur = conn.cursor()
        cur.execute("select record_pet_call()")
        assert cur.fetchone()[0] == 1, "첫 호출은 1"
        cur.execute("select record_pet_call()")
        assert cur.fetchone()[0] == 2, "같은 날 재호출은 누적"
    finally:
        as_admin(conn)

    assert _call_count(conn, user) == 2
    assert _call_count(conn, other_user) == 7, "남의 횟수는 안 건드린다"
