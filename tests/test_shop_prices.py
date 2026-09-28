"""시드된 상점 가격: 테마 50코인, 가구 30코인."""
from tests.conftest import requires_db

pytestmark = requires_db


def test_seeded_theme_and_furniture_prices(conn):
    cur = conn.cursor()
    cur.execute(
        "select type, array_agg(distinct price_coins) from items "
        "where type in ('theme', 'furniture') and name not like '테스트 %%' group by type"
    )
    assert dict(cur.fetchall()) == {"theme": [50], "furniture": [30]}
