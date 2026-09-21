"""ADR-22: 클라이언트가 코인·성장 컬럼을 직접 고치지 못하는지 검증한다.

RLS는 행 단위라 본인 행이면 모든 컬럼을 고칠 수 있었다. 컬럼 권한으로 좁힌 뒤,
막아야 할 것이 막히고 열어둔 것은 그대로 되는지 둘 다 본다.
"""
import uuid

import psycopg2
import pytest

from tests.conftest import as_admin, as_user, grant_coins, requires_db

pytestmark = requires_db


def _pet(conn, user_id: str) -> str:
    """관리자로 펫 하나를 만든다(슬롯 트리거는 관리자에게도 적용된다)."""
    pid = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "insert into pets (id, user_id, name) values (%s, %s, '초코')", (pid, user_id)
    )
    cur.close()
    return pid


def _forbidden(conn, user_id: str, sql: str, params: tuple):
    as_user(conn, user_id)
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            conn.cursor().execute(sql, params)
    finally:
        as_admin(conn)


# ── pets ────────────────────────────────────────────────────────────────

def test_client_cannot_raise_pet_level_or_affection(conn, user):
    pid = _pet(conn, user)
    _forbidden(conn, user, "update pets set level = 99 where id = %s", (pid,))
    _forbidden(conn, user, "update pets set affection = 100 where id = %s", (pid,))


def test_client_cannot_insert_pet_with_level(conn, user):
    """update만 막으면 insert 시점에 level을 심어 우회할 수 있다."""
    _forbidden(
        conn, user, "insert into pets (user_id, name, level) values (%s, '치트', 99)", (user,)
    )


def test_client_can_rename_pet_and_insert_first_pet(conn, user):
    as_user(conn, user)
    cur = conn.cursor()
    cur.execute("insert into pets (user_id, name) values (%s, '초코') returning id", (user,))
    pid = cur.fetchone()[0]
    cur.execute("update pets set name = '바둑이' where id = %s", (pid,))
    assert cur.rowcount == 1
    as_admin(conn)


# ── profiles ────────────────────────────────────────────────────────────

def test_client_cannot_raise_pet_slot_limit(conn, user):
    _forbidden(conn, user, "update profiles set pet_slot_limit = 99 where id = %s", (user,))


def test_client_can_update_allowed_profile_columns(conn, user):
    as_user(conn, user)
    cur = conn.cursor()
    cur.execute(
        "update profiles set goal_minutes = 45, nickname = '민형', fcm_token = 't' "
        "where id = %s",
        (user,),
    )
    assert cur.rowcount == 1
    as_admin(conn)


# ── user_items ──────────────────────────────────────────────────────────

def test_client_cannot_swap_item_id_but_can_equip(conn, user, item):
    """싼 아이템을 산 뒤 item_id를 비싼 것으로 바꿔치기하지 못해야 한다."""
    cur = conn.cursor()
    cur.execute("insert into user_items (user_id, item_id) values (%s, %s) returning id",
                (user, item))
    uid = cur.fetchone()[0]
    cur.close()

    _forbidden(conn, user, "update user_items set item_id = %s where id = %s", (item, uid))

    as_user(conn, user)
    cur = conn.cursor()
    cur.execute("update user_items set is_equipped = true where id = %s", (uid,))
    assert cur.rowcount == 1
    as_admin(conn)


# ── 펫 슬롯 한도 ─────────────────────────────────────────────────────────

def test_second_pet_is_rejected_until_slot_expands(conn, user, other_user):
    _pet(conn, other_user)  # 다른 유저의 펫은 내 한도에 안 센다
    _pet(conn, user)

    as_user(conn, user)
    with pytest.raises(psycopg2.errors.RaiseException, match="pet slot limit"):
        conn.cursor().execute("insert into pets (user_id, name) values (%s, '둘째')", (user,))
    as_admin(conn)

    conn.cursor().execute("update profiles set pet_slot_limit = 2 where id = %s", (user,))
    _pet(conn, user)  # 한도를 늘리면 들어간다


def test_buy_pet_slot_still_raises_limit(conn, user):
    """컬럼 권한을 회수해도 security definer RPC는 pet_slot_limit을 올릴 수 있어야 한다."""
    slot = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "insert into items (id, name, type, price_coins) values (%s, '슬롯', 'pet_slot', 50)",
        (slot,),
    )
    grant_coins(conn, user, 100)

    as_user(conn, user)
    conn.cursor().execute("select buy_item(%s, %s)", (slot, str(uuid.uuid4())))
    as_admin(conn)

    cur.execute("select pet_slot_limit from profiles where id = %s", (user,))
    assert cur.fetchone()[0] == 2
