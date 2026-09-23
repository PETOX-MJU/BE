"""ADR-32: coin_balance()가 본인 원장 합계만 돌려주는지 로컬 Supabase에서 검증한다."""
import psycopg2
import pytest

from tests.conftest import as_admin, as_user, balance, grant_coins, requires_db

pytestmark = requires_db


def _coin_balance(conn, user_id):
    as_user(conn, user_id)
    try:
        cur = conn.cursor()
        cur.execute("select coin_balance()")
        return cur.fetchone()[0]
    finally:
        as_admin(conn)


def test_empty_ledger_is_zero(conn, user):
    assert _coin_balance(conn, user) == 0


def test_sums_gains_and_spends(conn, user):
    grant_coins(conn, user, 100)
    grant_coins(conn, user, -30)
    grant_coins(conn, user, 5)

    assert _coin_balance(conn, user) == 75 == balance(conn, user)


def test_ignores_other_users_ledger(conn, user, other_user):
    grant_coins(conn, user, 10)
    grant_coins(conn, other_user, 500)

    assert _coin_balance(conn, user) == 10


def test_anon_cannot_call(conn):
    cur = conn.cursor()
    cur.execute("set role anon")
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            cur.execute("select coin_balance()")
    finally:
        cur.execute("reset role")
