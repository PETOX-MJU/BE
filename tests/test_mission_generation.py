"""이슈 #4(PR #3 리뷰 후속): generate_daily_missions()의 동시 실행을 검증한다.

buy_item/complete_mission과 같은 유형의 구멍이었다 — 유저별 "오늘 미션 있나"
체크(select) 후 없으면 insert인데 그 사이에 잠금이 없었다. 이 배치가 겹쳐서
두 번 돌면 같은 유저에게 오늘 미션이 중복 생성될 수 있었다(READ COMMITTED에서
두 트랜잭션이 서로의 커밋 전 상태를 못 보므로 둘 다 "없음"을 보고 둘 다 insert).
advisory lock으로 배치 전체를 직렬화해서 막는다.
"""
import threading

import psycopg2

from tests.conftest import LOCAL_DB_URL, requires_db

pytestmark = requires_db


def test_generate_daily_missions_concurrent_runs_do_not_duplicate(conn, user):
    """같은 함수를 동시에 두 번 호출해도 유저당 오늘 미션은 중복 없이 3개(앱 2 + 펫 1)여야 한다."""
    cur = conn.cursor()
    cur.execute("select id from detected_apps order by display_name limit 2")
    for (app_id,) in cur.fetchall():
        cur.execute(
            "insert into user_detected_apps (user_id, app_id) values (%s, %s)", (user, app_id)
        )
    cur.close()

    barrier = threading.Barrier(2)
    errors: list[str] = []

    def worker():
        c = psycopg2.connect(LOCAL_DB_URL)
        try:
            cur = c.cursor()
            barrier.wait(timeout=10)
            cur.execute("select generate_daily_missions()")
            c.commit()
        except Exception as e:  # noqa: BLE001 — 한쪽이 대기 타임아웃 나도 결과만 본다
            errors.append(type(e).__name__)
            c.rollback()
        finally:
            c.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    cur = conn.cursor()
    cur.execute(
        "select count(*) from user_missions um "
        "join missions m on m.id = um.mission_id "
        "where um.user_id = %s and m.type = 'daily' "
        "and m.valid_date = (now() at time zone 'Asia/Seoul')::date",
        (user,),
    )
    count = cur.fetchone()[0]
    assert count == 3, f"오늘 미션이 유저당 3개여야 하는데 {count}개다. (예외: {errors})"
