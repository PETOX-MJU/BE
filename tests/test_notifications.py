"""ADR-18(FR-057): users_to_notify_today()가 알림 대상을 정확히 거르는지 검증한다.

핵심 케이스는 notification_settings row가 없는 유저 — 가입 시 자동 생성되는
profiles와 달리 notification_settings는 자동 생성되지 않으므로, 그런 유저도
컬럼 기본값(mission_alert=true)대로 포함돼야 한다(coalesce 없으면 빠짐).
"""
from tests.conftest import requires_db

pytestmark = requires_db


def _set_token(conn, user_id, token):
    cur = conn.cursor()
    cur.execute("update profiles set fcm_token = %s where id = %s", (token, user_id))
    cur.close()


def _notified(conn):
    cur = conn.cursor()
    cur.execute("select user_id from users_to_notify_today()")
    rows = {r[0] for r in cur.fetchall()}
    cur.close()
    return rows


def test_user_with_no_settings_row_defaults_to_notified(conn, user, user_mission):
    """notification_settings row가 아예 없어도 기본값(true)대로 포함돼야 한다."""
    _set_token(conn, user, "token-1")
    assert user in _notified(conn)


def test_mission_alert_off_excludes_user(conn, user, user_mission):
    _set_token(conn, user, "token-1")
    cur = conn.cursor()
    cur.execute(
        "insert into notification_settings (user_id, mission_alert) values (%s, false)",
        (user,),
    )
    cur.close()
    assert user not in _notified(conn)


def test_no_fcm_token_excludes_user(conn, user, user_mission):
    assert user not in _notified(conn)


def test_no_mission_today_excludes_user(conn, user):
    """오늘자 daily 미션이 없으면(user_mission 픽스처 미사용) 대상에서 빠진다."""
    _set_token(conn, user, "token-1")
    assert user not in _notified(conn)
