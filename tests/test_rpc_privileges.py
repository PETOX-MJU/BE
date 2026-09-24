"""anon이 실행할 수 있는 public 함수가 없어야 한다.

CREATE FUNCTION은 PUBLIC에 execute를 자동으로 줘서, 새 RPC를 만들 때 revoke를 빠뜨리면
로그인 없이 호출된다. 트리거 함수는 직접 호출이 불가능하므로 제외한다.
"""
from tests.conftest import requires_db

pytestmark = requires_db


def _functions_executable_by(conn, role):
    cur = conn.cursor()
    cur.execute(
        """select p.proname from pg_proc p join pg_namespace n on n.oid = p.pronamespace
           where n.nspname = 'public' and p.prokind = 'f'
             and p.prorettype <> 'trigger'::regtype
             and has_function_privilege(%s, p.oid, 'execute')""",
        (role,),
    )
    return {r[0] for r in cur.fetchall()}


def test_anon_cannot_execute_any_rpc(conn):
    assert _functions_executable_by(conn, "anon") == set()


def test_notify_query_is_service_role_only(conn):
    assert "users_to_notify_today" not in _functions_executable_by(conn, "authenticated")
    assert "users_to_notify_today" in _functions_executable_by(conn, "service_role")
