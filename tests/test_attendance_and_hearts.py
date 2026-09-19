"""ADR-27/28: check_in()과 pet_interact()를 로컬 Supabase에서 검증한다.

둘 다 코인·성장이 걸려 있어 클라이언트가 직접 쓰지 못하고 RPC만 쓴다. 날짜는 전부
DB의 KST 기준이다.
"""
import uuid

import psycopg2
import pytest

from tests.conftest import as_admin, as_user, balance, requires_db

pytestmark = requires_db


def _kst_today(conn):
    cur = conn.cursor()
    cur.execute("select (now() at time zone 'Asia/Seoul')::date")
    return cur.fetchone()[0]


def _seed_attendance(conn, user_id, day_offsets):
    cur = conn.cursor()
    for off in day_offsets:
        cur.execute(
            "insert into attendance (user_id, attended_on) "
            "values (%s, (now() at time zone 'Asia/Seoul')::date + %s)",
            (user_id, off),
        )
    cur.close()


def _check_in(conn, user_id):
    as_user(conn, user_id)
    try:
        cur = conn.cursor()
        cur.execute("select streak, coins_awarded from check_in()")
        return cur.fetchone()
    finally:
        as_admin(conn)


# ── 출석체크 ─────────────────────────────────────────────────────────────

def test_first_check_in_records_kst_today_and_pays_five(conn, user):
    assert _check_in(conn, user) == (1, 5)

    cur = conn.cursor()
    cur.execute("select attended_on from attendance where user_id = %s", (user,))
    assert [r[0] for r in cur.fetchall()] == [_kst_today(conn)]
    assert balance(conn, user) == 5


def test_checking_in_twice_the_same_day_pays_once(conn, user):
    _check_in(conn, user)
    assert _check_in(conn, user) == (1, 0)
    assert balance(conn, user) == 5


def test_seventh_consecutive_day_adds_the_streak_bonus(conn, user):
    _seed_attendance(conn, user, range(-6, 0))  # 어제까지 6일 연속

    assert _check_in(conn, user) == (7, 35), "5 + 연속 7일 보너스 30"
    assert balance(conn, user) == 35


def test_a_missed_day_restarts_the_streak(conn, user):
    _seed_attendance(conn, user, [-1, -3])  # -2일이 비었다

    assert _check_in(conn, user) == (2, 5)


def test_client_cannot_write_or_read_others_attendance(conn, user, other_user):
    _seed_attendance(conn, other_user, [-1])

    as_user(conn, user)
    try:
        cur = conn.cursor()
        cur.execute("select count(*) from attendance")
        assert cur.fetchone()[0] == 0, "남의 출석은 안 보인다"
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(
                "insert into attendance (user_id, attended_on) values (%s, current_date)",
                (user,),
            )
    finally:
        as_admin(conn)
    assert balance(conn, user) == 0


# ── 하트 ────────────────────────────────────────────────────────────────

def _pet(conn, user_id, affection=0):
    pid = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "insert into pets (id, user_id, name, affection) values (%s, %s, '초코', %s)",
        (pid, user_id, affection),
    )
    cur.close()
    return pid


def _interact(conn, user_id, pet_id):
    as_user(conn, user_id)
    try:
        cur = conn.cursor()
        cur.execute("select new_affection, hearts_gained from pet_interact(%s)", (pet_id,))
        return cur.fetchone()
    finally:
        as_admin(conn)


def _affection(conn, pet_id):
    cur = conn.cursor()
    cur.execute("select affection from pets where id = %s", (pet_id,))
    return cur.fetchone()[0]


def test_each_interaction_adds_five(conn, user):
    pet = _pet(conn, user)
    assert _interact(conn, user, pet) == (5, 5)
    assert _interact(conn, user, pet) == (10, 5)
    assert _affection(conn, pet) == 10


def test_daily_cap_stops_at_fifty_per_pet(conn, user):
    pet = _pet(conn, user)
    results = [_interact(conn, user, pet) for _ in range(12)]

    assert [g for _, g in results] == [5] * 10 + [0, 0]
    assert _affection(conn, pet) == 50


def test_the_cap_resets_the_next_day(conn, user):
    pet = _pet(conn, user)
    cur = conn.cursor()
    cur.execute(
        "insert into pet_interactions (pet_id, interacted_on, gained) "
        "values (%s, (now() at time zone 'Asia/Seoul')::date - 1, 50)",
        (pet,),
    )

    assert _interact(conn, user, pet) == (5, 5), "어제 50을 채웠어도 오늘은 다시 시작"


def test_affection_never_exceeds_one_hundred(conn, user):
    pet = _pet(conn, user, affection=98)

    assert _interact(conn, user, pet) == (100, 2), "남은 만큼만 오른다"
    assert _interact(conn, user, pet) == (100, 0)


def test_cannot_interact_with_someone_elses_pet(conn, user, other_user):
    pet = _pet(conn, other_user)

    with pytest.raises(psycopg2.errors.RaiseException, match="pet not found"):
        _interact(conn, user, pet)
    assert _affection(conn, pet) == 0


def test_client_cannot_read_others_interactions_or_write_any(conn, user, other_user):
    pet = _pet(conn, other_user)
    _interact(conn, other_user, pet)

    as_user(conn, user)
    try:
        cur = conn.cursor()
        cur.execute("select count(*) from pet_interactions")
        assert cur.fetchone()[0] == 0
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute(
                "insert into pet_interactions (pet_id, interacted_on, gained) "
                "values (%s, current_date, 1)",
                (pet,),
            )
    finally:
        as_admin(conn)
