"""ADR-33: 가입 트리거가 user_metadata의 nickname을 profiles로 복사하는지 검증한다."""
import json
import uuid

import pytest

from tests.conftest import requires_db

pytestmark = requires_db


def _signup(conn, metadata):
    uid = str(uuid.uuid4())
    cur = conn.cursor()
    cur.execute(
        """insert into auth.users (id, instance_id, aud, role, email, encrypted_password,
                                   raw_user_meta_data, created_at, updated_at)
           values (%s, '00000000-0000-0000-0000-000000000000', 'authenticated',
                   'authenticated', %s, '', %s, now(), now())""",
        (uid, f"{uid}@test.local", json.dumps(metadata) if metadata is not None else None),
    )
    cur.execute("select nickname from profiles where id = %s", (uid,))
    return cur.fetchone()[0]


def test_copies_nickname_from_metadata(conn):
    assert _signup(conn, {"nickname": "민형"}) == "민형"


def test_trims_surrounding_spaces(conn):
    assert _signup(conn, {"nickname": "  민형 "}) == "민형"


@pytest.mark.parametrize("metadata", [None, {}, {"nickname": "   "}, {"full_name": "이름"}])
def test_missing_or_blank_nickname_stays_null(conn, metadata):
    assert _signup(conn, metadata) is None


def test_kakao_signup_uses_profile_name(conn):
    """카카오는 nickname 키 없이 preferred_username·name 등에 프로필 이름을 넣는다."""
    kakao = {"name": "카카오이름", "preferred_username": "카카오이름", "user_name": "카카오이름"}
    assert _signup(conn, kakao) == "카카오이름"


def test_nickname_key_wins_over_provider_name(conn):
    assert _signup(conn, {"nickname": "앱닉네임", "preferred_username": "카카오", "name": "카카오"}) == "앱닉네임"


def test_falls_back_to_name_when_preferred_username_blank(conn):
    assert _signup(conn, {"preferred_username": " ", "name": "카카오이름"}) == "카카오이름"
