"""ADR-004가 주장하는 신뢰 경계가 실제로 강제되는지 검증한다.

주장은 셋이다.
  1. coin_ledger·user_items는 RPC만 쓸 수 있다 (클라이언트 직접 쓰기 불가)
  2. request_id 멱등키로 재시도해도 정확히 한 번만 처리된다
  3. 구매는 트랜잭션이라 반쪽 실패가 없다

세 번째와 별개로, 서로 다른 요청이 동시에 들어올 때도 잔액이 지켜지는지는
멱등키가 보장하지 않는다. 마지막 테스트가 그 지점을 본다.
"""
import uuid

import psycopg2
import pytest

from tests.conftest import (
    as_admin,
    as_user,
    balance,
    grant_coins,
    insert_item,
    requires_db,
    run_concurrently,
)

pytestmark = requires_db


# ── 1. RLS: 클라이언트는 원장에 직접 쓸 수 없다 ──────────────────────────

def test_client_cannot_insert_into_coin_ledger(conn, user):
    """조작된 클라이언트가 코인을 스스로 지급하지 못해야 한다."""
    grant_coins(conn, user, 0)
    as_user(conn, user)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur = conn.cursor()
        cur.execute(
            "insert into coin_ledger (user_id, amount, reason) values (%s, 9999, 'hack')",
            (user,),
        )
    as_admin(conn)
    assert balance(conn, user) == 0


def test_client_cannot_insert_into_user_items(conn, user, item):
    """구매를 거치지 않고 아이템을 넣지 못해야 한다."""
    as_user(conn, user)
    with pytest.raises(psycopg2.errors.InsufficientPrivilege):
        cur = conn.cursor()
        cur.execute(
            "insert into user_items (user_id, item_id) values (%s, %s)", (user, item)
        )
    as_admin(conn)


def test_cannot_read_other_users_ledger(conn, user, other_user):
    """RLS 격리 — 남의 원장은 0행으로 보인다."""
    grant_coins(conn, other_user, 500)
    as_user(conn, user)
    cur = conn.cursor()
    cur.execute("select count(*) from coin_ledger where user_id = %s", (other_user,))
    assert cur.fetchone()[0] == 0
    as_admin(conn)


# ── 2. 멱등성 ────────────────────────────────────────────────────────────

def test_buy_item_is_idempotent(conn, user, item):
    """같은 request_id로 두 번 호출해도 한 번만 차감된다."""
    grant_coins(conn, user, 100)
    req = str(uuid.uuid4())

    as_user(conn, user)
    cur = conn.cursor()
    cur.execute("select buy_item(%s, %s)", (item, req))
    cur.execute("select buy_item(%s, %s)", (item, req))  # 재시도
    as_admin(conn)

    assert balance(conn, user) == 40, "60코인이 한 번만 빠져야 한다"
    cur = conn.cursor()
    cur.execute("select count(*) from user_items where user_id = %s", (user,))
    assert cur.fetchone()[0] == 1, "아이템도 한 개만 들어와야 한다"


# ── 3. 잔액 부족 시 반쪽 실패가 없다 ──────────────────────────────────────

def test_insufficient_balance_changes_nothing(conn, user, item):
    """코인이 모자라면 원장도 아이템도 그대로여야 한다."""
    grant_coins(conn, user, 10)  # 60짜리를 살 수 없다
    before = balance(conn, user)

    as_user(conn, user)
    with pytest.raises(psycopg2.errors.RaiseException):
        cur = conn.cursor()
        cur.execute("select buy_item(%s, %s)", (item, str(uuid.uuid4())))
    as_admin(conn)

    assert balance(conn, user) == before
    cur = conn.cursor()
    cur.execute("select count(*) from user_items where user_id = %s", (user,))
    assert cur.fetchone()[0] == 0


# ── 4. 동시성 — 멱등키가 막지 못하는 구간 ─────────────────────────────────

def test_concurrent_buys_must_not_overdraw(conn, user, item):
    """서로 다른 request_id의 동시 구매가 잔액을 넘기지 못해야 한다.

    잔액 100, 가격 60 — 하나만 성공해야 한다. buy_item은 SUM으로 잔액을 읽고
    INSERT 하는데 그 사이에 잠금이 없다. 두 트랜잭션이 같은 잔액을 읽으면
    둘 다 검사를 통과한다.

    서로 다른 아이템을 산다. 같은 아이템이면 중복 구매 규칙(ADR-34)이 먼저 막아서
    잠금이 없어도 통과해 버린다.
    """
    grant_coins(conn, user, 100)
    items = iter([item, insert_item(conn)])
    errors = run_concurrently(
        2, lambda cur: cur.execute("select buy_item(%s, %s)", (next(items), str(uuid.uuid4()))), user
    )

    final = balance(conn, user)
    assert final >= 0, (
        f"잔액이 {final}로 음수다. 동시 구매 두 건이 같은 잔액을 읽고 "
        f"둘 다 통과했다 — buy_item에 사용자 단위 잠금이 없다. (예외: {errors})"
    )
    assert final == 40, f"한 건만 성공해 40이어야 하는데 {final}이다. (예외: {errors})"


def test_concurrent_mission_completes_pay_once(conn, user, finished_mission):
    """같은 미션을 동시에 두 번 완료해도 보상은 한 번만 지급돼야 한다.

    complete_mission은 상태를 select로 읽고 update한다. update는 행 잠금이
    걸리지만, 뒤늦은 쪽이 이미 'in_progress'를 읽어둔 뒤라 잠금이 풀리면 그대로
    진행한다. update에 status 조건도 없어서 두 번째도 보상을 넣는다.

    순차 호출로는 재현되지 않는다(두 번째 select가 이미 completed를 본다).
    실제로 겹치게 하려면 스레드로 돌려야 한다.
    """

    errors = run_concurrently(
        2,
        lambda cur: cur.execute(
            "select complete_mission(%s, %s)", (finished_mission, str(uuid.uuid4()))
        ),
        user,
    )

    final = balance(conn, user)
    assert final == 50, (
        f"보상 50이 한 번만 들어와야 하는데 {final}이다. "
        f"두 호출 모두 in_progress를 읽고 각자 보상을 지급했다. (예외: {errors})"
    )
