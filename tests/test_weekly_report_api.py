"""ADR-011 GET /reports/weekly의 해석 로직(비교%·문구)을 단위 테스트한다.

JWT 검증(get_current_user_id)과 실제 RPC 호출(get_weekly_report_rows)은
app.dependency_overrides로 갈아끼운다 — 이 파일은 SQL이 돌려준 합계를 FastAPI가
퍼센트·문구로 어떻게 바꾸는지만 본다. RPC 자체(auth.uid() 필터, RLS)는
tests/test_weekly_report.py가 로컬 Supabase로 따로 검증한다.
"""
import pytest
from fastapi.testclient import TestClient

from app.main import (
    app,
    get_current_user_id,
    get_weekly_report_by_app_rows,
    get_weekly_report_daily_rows,
    get_weekly_report_rows,
)

client = TestClient(app)


@pytest.fixture(autouse=True)
def _fake_login():
    app.dependency_overrides[get_current_user_id] = lambda: "test-user-id"
    # 이 파일은 지난주/이번주 비교%·문구 로직만 본다 — daily/by_app은 기본
    # 빈 리스트로 깔아두고, 그 필드 자체를 보는 테스트만 따로 채운다.
    app.dependency_overrides[get_weekly_report_daily_rows] = lambda: []
    app.dependency_overrides[get_weekly_report_by_app_rows] = lambda: []
    yield
    app.dependency_overrides.clear()


def _set_rows(rows):
    app.dependency_overrides[get_weekly_report_rows] = lambda: rows


def test_usage_decreased_reports_negative_change_and_message():
    _set_rows(
        [
            {"week": "지난주", "total_minutes": 385},
            {"week": "이번주", "total_minutes": 260},
        ]
    )
    resp = client.get("/reports/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_week_minutes"] == 385
    assert body["this_week_minutes"] == 260
    assert body["change_pct"] == -32.5
    assert body["message"] == "지난주보다 32.5% 줄였어요!"


def test_usage_increased_reports_positive_change_and_message():
    _set_rows(
        [
            {"week": "지난주", "total_minutes": 100},
            {"week": "이번주", "total_minutes": 150},
        ]
    )
    resp = client.get("/reports/weekly")
    body = resp.json()
    assert body["change_pct"] == 50.0
    assert body["message"] == "지난주보다 50.0% 늘었어요. 다음주엔 목표를 다시 세워봐요."


def test_usage_unchanged_reports_zero_change_and_neutral_message():
    _set_rows(
        [
            {"week": "지난주", "total_minutes": 100},
            {"week": "이번주", "total_minutes": 100},
        ]
    )
    resp = client.get("/reports/weekly")
    body = resp.json()
    assert body["change_pct"] == 0
    assert "똑같아요" in body["message"]
    assert "줄였어요" not in body["message"]
    assert "늘었어요" not in body["message"]


def test_no_last_week_data_does_not_divide_by_zero():
    _set_rows([{"week": "이번주", "total_minutes": 40}])
    resp = client.get("/reports/weekly")
    assert resp.status_code == 200
    body = resp.json()
    assert body["last_week_minutes"] == 0
    assert body["change_pct"] is None
    assert "기록이 없어요" in body["message"]


def test_no_data_at_all_does_not_divide_by_zero():
    _set_rows([])
    resp = client.get("/reports/weekly")
    assert resp.status_code == 200
    assert resp.json()["change_pct"] is None


def test_without_auth_is_rejected():
    app.dependency_overrides.clear()  # get_current_user_id override 제거 -> 실제 검증 태움
    resp = client.get("/reports/weekly")
    assert resp.status_code == 401


def test_daily_rows_are_passed_through_as_date_minutes_pairs():
    """이슈 #16: 일별 그래프용 데이터가 응답에 그대로 실리는지 본다.

    RPC 자체(7일 전부 채워지는지, 남의 데이터 안 섞이는지)는
    tests/test_weekly_report.py가 로컬 Supabase로 따로 검증한다.
    """
    _set_rows([])
    app.dependency_overrides[get_weekly_report_daily_rows] = lambda: [
        {"usage_date": "2026-09-10", "total_minutes": 42},
        {"usage_date": "2026-09-11", "total_minutes": 0},
    ]
    resp = client.get("/reports/weekly")
    assert resp.json()["daily"] == [
        {"date": "2026-09-10", "minutes": 42},
        {"date": "2026-09-11", "minutes": 0},
    ]


def test_by_app_rows_are_passed_through_as_app_minutes_pairs():
    _set_rows([])
    app.dependency_overrides[get_weekly_report_by_app_rows] = lambda: [
        {"app_name": "틱톡", "total_minutes": 120},
        {"app_name": "유튜브 쇼츠", "total_minutes": 60},
    ]
    resp = client.get("/reports/weekly")
    assert resp.json()["by_app"] == [
        {"app_name": "틱톡", "minutes": 120},
        {"app_name": "유튜브 쇼츠", "minutes": 60},
    ]
