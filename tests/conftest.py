"""로컬 Supabase Postgres에 붙는 테스트 픽스처.

RPC(security definer)와 RLS는 실제 Postgres에서만 검증되므로, FastAPI를 거치지
않고 DB에 직접 붙는다. `supabase start`로 띄운 로컬 인스턴스를 쓰고, 원격
프로젝트는 절대 건드리지 않는다.
"""
import os
import threading
import uuid

import psycopg2
import pytest

# supabase start 기본 로컬 DB. 환경변수로 덮어쓸 수 있다.
LOCAL_DB_URL = os.getenv(
    "TEST_DATABASE_URL", "postgresql://postgres:postgres@127.0.0.1:54322/postgres"
)


def _connect():
    return psycopg2.connect(LOCAL_DB_URL)


def db_available() -> bool:
    try:
        _connect().close()
        return True
    except psycopg2.Error:
        return False


_db_ok = db_available()

# CI에서는 스킵을 허용하지 않는다. 스킵된 테스트는 없는 테스트와 같아서,
# supabase start가 조용히 실패하면 잠금이 지워져도 초록으로 통과한다.
if not _db_ok and os.getenv("CI"):
    raise RuntimeError(f"CI인데 {LOCAL_DB_URL}에 붙지 못했다. supabase start를 확인할 것.")

requires_db = pytest.mark.skipif(
    not _db_ok,
    reason="로컬 Supabase가 없다. `supabase start` 후 다시 실행할 것.",
)


@pytest.fixture
def conn():
    """관리자 권한 연결. 픽스처 준비와 검증용."""
    c = _connect()
    c.autocommit = True
    yield c
    c.close()


def as_user(connection, user_id: str):
    """이 연결의 이후 쿼리를 해당 사용자로 실행한다.

    RLS 정책이 auth.uid()를 보므로, JWT 클레임을 세션에 심어 로그인 상태를
    흉내낸다. role을 authenticated로 낮춰야 정책이 실제로 적용된다.
    """
    cur = connection.cursor()
    cur.execute("select set_config('request.jwt.claims', %s, false)",
                ('{"sub":"%s","role":"authenticated"}' % user_id,))
    cur.execute("set role authenticated")
    cur.close()


def as_admin(connection):
    cur = connection.cursor()
    cur.execute("reset role")
    cur.execute("select set_config('request.jwt.claims', NULL, false)")
    cur.close()


@pytest.fixture
def user(conn):
    """auth.users에 사용자 하나. profiles는 트리거가 자동 생성한다."""
    uid = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        """insert into auth.users (id, instance_id, aud, role, email,
                                   encrypted_password, created_at, updated_at)
           values (%s, '00000000-0000-0000-0000-000000000000', 'authenticated',
                   'authenticated', %s, '', now(), now())""",
        (uid, f"{uid}@test.local"),
    )
    cur.close()
    yield uid


@pytest.fixture
def other_user(conn):
    uid = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        """insert into auth.users (id, instance_id, aud, role, email,
                                   encrypted_password, created_at, updated_at)
           values (%s, '00000000-0000-0000-0000-000000000000', 'authenticated',
                   'authenticated', %s, '', now(), now())""",
        (uid, f"{uid}@test.local"),
    )
    cur.close()
    yield uid


@pytest.fixture
def item(conn):
    """가격 60코인짜리 의류 아이템. type은 clothing / pet_slot 둘만 허용된다."""
    iid = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        "insert into items (id, name, type, price_coins) values (%s, %s, %s, %s)",
        (iid, "테스트 모자", "clothing", 60),
    )
    cur.close()
    yield iid


def grant_coins(connection, user_id: str, amount: int):
    """RPC를 우회해 원장에 직접 지급. 잔액 조건을 만들기 위한 픽스처 전용."""
    cur = connection.cursor()
    cur.execute(
        "insert into coin_ledger (user_id, amount, reason, request_id) "
        "values (%s, %s, 'test_seed', %s)",
        (user_id, amount, str(uuid.uuid4())),
    )
    cur.close()


def balance(connection, user_id: str) -> int:
    cur = connection.cursor()
    cur.execute(
        "select coalesce(sum(amount), 0) from coin_ledger where user_id = %s",
        (user_id,),
    )
    v = cur.fetchone()[0]
    cur.close()
    return v


def _make_mission(connection, user_id: str, day_offset: int) -> str:
    """보상 50코인, 30분 이내 목표의 진행중 미션. day_offset은 KST 오늘 기준(0=오늘, -1=어제)."""
    mid, umid = str(uuid.uuid4()), str(uuid.uuid4())
    cur = connection.cursor()
    cur.execute(
        "insert into missions (id, type, title, target_minutes, reward_coins, valid_date) "
        "values (%s, 'daily', '테스트 미션', 30, 50, "
        "(now() at time zone 'Asia/Seoul')::date + %s)",
        (mid, day_offset),
    )
    cur.execute(
        "insert into user_missions (id, user_id, mission_id, status, coins_earned) "
        "values (%s, %s, %s, 'in_progress', 0)",
        (umid, user_id, mid),
    )
    cur.close()
    return umid


@pytest.fixture
def user_mission(conn, user):
    """오늘(KST) 시작한 진행중 미션 하나."""
    yield _make_mission(conn, user, 0)


@pytest.fixture
def finished_mission(conn, user):
    """어제(KST) 끝난 진행중 미션 하나. 사용 기록이 없어 목표를 지킨 상태다."""
    yield _make_mission(conn, user, -1)


def run_concurrently(n: int, action, user_id: str) -> list[str]:
    """같은 사용자로 action을 n개 스레드에서 동시에 실행하고 예외 이름을 모은다.

    barrier로 출발선을 맞춰야 실제로 겹친다. 한 연결에서 두 번 부르면 트랜잭션이
    직렬화되어 경합이 재현되지 않는다.
    """
    barrier = threading.Barrier(n)
    errors: list[str] = []
    lock = threading.Lock()

    def worker():
        c = psycopg2.connect(LOCAL_DB_URL)
        try:
            as_user(c, user_id)
            cur = c.cursor()
            cur.execute("set local statement_timeout = '10s'")
            barrier.wait(timeout=10)
            action(cur)
            c.commit()
        except Exception as e:  # noqa: BLE001 — 한쪽이 거부되는 건 정상 동작
            with lock:
                errors.append(type(e).__name__)
            c.rollback()
        finally:
            c.close()

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return errors
