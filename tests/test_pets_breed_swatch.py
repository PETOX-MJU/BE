"""ADR-36: 캐릭터 백업 칸(견종·스와치)을 FE가 쓸 수 있고, breeds.json 에 없는 이름은 막는다."""
import psycopg2
import pytest

from tests.conftest import as_admin, as_user, requires_db

pytestmark = requires_db


def _as(conn, user_id, sql, params):
    as_user(conn, user_id)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone() if cur.description else None
    finally:
        as_admin(conn)


def test_client_can_save_breed_and_swatches(conn, user):
    (pid,) = _as(
        conn, user,
        "insert into pets (user_id, name, breed, main_swatch, sub_swatch) "
        "values (%s, '초코', 'shiba', 'red', 'cream') returning id",
        (user,),
    )
    _as(conn, user, "update pets set main_swatch = 'white', sub_swatch = null where id = %s", (pid,))

    cur = conn.cursor()
    cur.execute("select breed, main_swatch, sub_swatch from pets where id = %s", (pid,))
    assert cur.fetchone() == ("shiba", "white", None)


def test_pet_without_character_values_still_saves(conn, user):
    """지금 FE는 세 값을 보내지 않는다."""
    assert _as(conn, user, "insert into pets (user_id, name) values (%s, '초코') returning id", (user,))


@pytest.mark.parametrize("column,value", [
    ("breed", "poodle"),
    ("breed", "Shiba"),
    ("main_swatch", "pink"),
    ("sub_swatch", "#ffffff"),
])
def test_names_outside_breeds_json_are_rejected(conn, user, column, value):
    with pytest.raises(psycopg2.errors.CheckViolation):
        _as(conn, user, f"insert into pets (user_id, name, {column}) values (%s, '초코', %s)", (user, value))
