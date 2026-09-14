"""ADR-010 JWT 검증(get_current_user_id)을 자체 서명 토큰으로 단위 테스트한다.

실제 Supabase JWKS를 fetch하지 않는다 — jwks_client.get_signing_key_from_jwt를
테스트 전용 키로 monkeypatch해서, "서명이 맞으면 통과·틀리면 401"만 검증한다.
"""
import uuid

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

import app.main as main

client = TestClient(main.app)


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


def _patch_jwks(monkeypatch, public_key):
    monkeypatch.setattr(
        main.jwks_client,
        "get_signing_key_from_jwt",
        lambda token: _FakeSigningKey(public_key),
    )


def test_me_without_token_is_rejected():
    resp = client.get("/me")
    assert resp.status_code == 401


def test_me_with_valid_token_returns_user_id(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, private_key.public_key())

    user_id = str(uuid.uuid4())
    token = jwt.encode(
        {"sub": user_id, "aud": "authenticated"}, private_key, algorithm="ES256"
    )

    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json() == {"user_id": user_id}


def test_me_with_wrong_audience_is_rejected(monkeypatch):
    private_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, private_key.public_key())

    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "anon"}, private_key, algorithm="ES256"
    )

    resp = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_me_with_wrong_signing_key_is_rejected(monkeypatch):
    real_key = ec.generate_private_key(ec.SECP256R1())
    attacker_key = ec.generate_private_key(ec.SECP256R1())
    _patch_jwks(monkeypatch, real_key.public_key())

    # 공격자가 자기 개인키로 서명한 토큰 — 서버는 real_key의 공개키로만 검증하므로 불일치.
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "aud": "authenticated"},
        attacker_key,
        algorithm="ES256",
    )

    resp = client.get("/me", headers={"Authorization": f"Bearer {forged}"})
    assert resp.status_code == 401
