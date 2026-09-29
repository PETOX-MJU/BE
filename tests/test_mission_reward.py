"""ADR-39: 미션 판정이 서버로 돌아왔다. 서버 미션 스케줄이 켜져 있고,
ADR-37의 폰 보상 RPC(claim_mission_reward)는 클라이언트가 부를 수 없어야 한다.
"""
import psycopg2
import pytest

from tests.conftest import as_admin, as_user, balance, requires_db

pytestmark = requires_db


def test_server_mission_schedules_are_on(conn):
    cur = conn.cursor()
    cur.execute(
        "select jobname, schedule from cron.job where jobname in "
        "('generate-daily-missions', 'settle-missions', 'send-mission-notifications') "
        "order by jobname"
    )
    assert cur.fetchall() == [
        ("generate-daily-missions", "10 15 * * *"),
        ("settle-missions", "5 15 * * *"),
    ], "알림 cron은 FCM이 붙을 때까지 꺼 둔다 (20260929090000)"


def test_client_cannot_claim_phone_mission_reward(conn, user):
    """서버 정산과 함께 열려 있으면 같은 날 코인이 두 번 나간다."""
    as_user(conn, user)
    try:
        with pytest.raises(psycopg2.errors.InsufficientPrivilege):
            conn.cursor().execute(
                "select claim_mission_reward('daily', (now() at time zone 'Asia/Seoul')::date)"
            )
    finally:
        as_admin(conn)
    assert balance(conn, user) == 0
