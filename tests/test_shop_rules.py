"""ADR-34: buy_item의 구매 규칙(중복 불가·테마 먼저·순서대로)과 카탈로그 시드를 검증한다."""
import uuid

import psycopg2
import pytest

from tests.conftest import as_admin, as_user, balance, grant_coins, insert_item, requires_db

pytestmark = requires_db


def _buy(conn, user_id, item_id, request_id=None):
    as_user(conn, user_id)
    try:
        conn.cursor().execute("select buy_item(%s, %s)", (item_id, request_id or str(uuid.uuid4())))
    finally:
        as_admin(conn)


def _theme_with_items(conn, n=3):
    theme = insert_item(conn, "theme", 10)
    return theme, [insert_item(conn, "furniture", 10, theme, i) for i in range(1, n + 1)]


def _rejects(conn, user_id, item_id, message):
    before = balance(conn, user_id)
    with pytest.raises(psycopg2.errors.RaiseException, match=message):
        _buy(conn, user_id, item_id)
    assert balance(conn, user_id) == before, "거부된 구매는 코인을 건드리지 않는다"


def test_cannot_buy_the_same_item_twice(conn, user, item):
    grant_coins(conn, user, 200)
    _buy(conn, user, item)
    _rejects(conn, user, item, "이미 보유한 아이템입니다")


def test_retry_with_same_request_id_is_silent_not_duplicate_error(conn, user, item):
    grant_coins(conn, user, 200)
    req = str(uuid.uuid4())
    _buy(conn, user, item, req)
    _buy(conn, user, item, req)  # 멱등 확인이 규칙 확인보다 앞선다
    assert balance(conn, user) == 140


def test_theme_item_needs_the_theme_first(conn, user):
    grant_coins(conn, user, 100)
    _, (first, *_) = _theme_with_items(conn)
    _rejects(conn, user, first, "테마를 먼저 구매해야 합니다")


def test_items_must_be_bought_in_order(conn, user):
    grant_coins(conn, user, 100)
    theme, (first, second, third) = _theme_with_items(conn)
    _buy(conn, user, theme)

    _rejects(conn, user, second, "앞 단계 아이템을 먼저 구매해야 합니다")
    _buy(conn, user, first)
    _rejects(conn, user, third, "앞 단계 아이템을 먼저 구매해야 합니다")
    _buy(conn, user, second)
    _buy(conn, user, third)
    assert balance(conn, user) == 60


def test_pet_slot_can_be_bought_repeatedly(conn, user):
    grant_coins(conn, user, 100)
    slot = insert_item(conn, "pet_slot", 10)
    _buy(conn, user, slot)
    _buy(conn, user, slot)

    cur = conn.cursor()
    cur.execute("select pet_slot_limit from profiles where id = %s", (user,))
    assert cur.fetchone()[0] == 3


def test_seed_has_four_themes_with_four_ordered_items(conn):
    cur = conn.cursor()
    cur.execute(
        """select t.name, array_agg(i.sort_order order by i.sort_order)
           from items i join items t on t.id = i.theme_id
           where t.name in ('홈', '해변', '빙하', '캠핑장')
           group by t.name"""
    )
    assert dict(cur.fetchall()) == {n: [1, 2, 3, 4] for n in ("홈", "해변", "빙하", "캠핑장")}
