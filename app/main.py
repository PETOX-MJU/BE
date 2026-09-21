import os

import httpx
import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, EmailStr
from supabase import create_client

load_dotenv()

app = FastAPI(title="peTox API")

supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

# ADR-010: Supabase가 이미 비대칭키(JWT Signing Keys)로 전환했으므로 JWKS를
# 공개 엔드포인트에서 가져와 로컬로 서명을 검증한다. 새 시크릿 불필요.
security = HTTPBearer()
jwks_client = PyJWKClient(f"{os.environ['SUPABASE_URL']}/auth/v1/.well-known/jwks.json")
JWT_AUDIENCE = "authenticated"  # ADR-010: Supabase가 로그인 세션 토큰에 항상 넣는 aud 값


def get_jwks_client() -> PyJWKClient:
    """테스트에서 app.dependency_overrides로 교체하기 위한 진입점."""
    return jwks_client


def get_current_user_id(
    creds: HTTPAuthorizationCredentials = Depends(security),
    jwks: PyJWKClient = Depends(get_jwks_client),
) -> str:
    token = creds.credentials
    try:
        signing_key = jwks.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256"],  # 이 프로젝트 JWKS가 실제로 쓰는 알고리즘만 허용(curl로 확인)
            audience=JWT_AUDIENCE,
        )
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"invalid token: {e}")
    return payload["sub"]


@app.get("/health")
def health():
    return {"status": "ok"}


class SignUpRequest(BaseModel):
    email: EmailStr
    password: str


@app.post("/auth/signup")
def signup(payload: SignUpRequest):
    try:
        result = supabase.auth.sign_up(
            {"email": payload.email, "password": payload.password}
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"user_id": result.user.id if result.user else None}


@app.get("/me")
def me(user_id: str = Depends(get_current_user_id)):
    return {"user_id": user_id}


def _call_report_rpc(rpc_name: str, access_token: str, week_offset: int) -> list[dict]:
    """리포트 계열 RPC를 호출자 본인의 JWT로 호출한다.

    ADR-011: 전역 supabase 클라이언트(anon key, 로그인 세션 없음)를 그대로 쓰면
    Postgres에서 auth.uid()가 NULL이 돼서 0행만 나온다. 이 유저로 인증된
    요청이어야 각 RPC의 auth.uid() 필터가 본인 데이터를 잡는다. 전역
    클라이언트를 mutate하지 않는 이유는 동시 요청 간 세션이 서로 덮어써지는
    걸 막기 위해서다 — 요청마다 별도 HTTP 호출로 격리한다.
    """
    resp = httpx.post(
        f"{os.environ['SUPABASE_URL']}/rest/v1/rpc/{rpc_name}",
        headers={
            "apikey": os.environ["SUPABASE_KEY"],
            "Authorization": f"Bearer {access_token}",
        },
        json={"p_week_offset": week_offset},
        timeout=5.0,
    )
    resp.raise_for_status()
    return resp.json()


def call_weekly_report_rpc(access_token: str, week_offset: int) -> list[dict]:
    return _call_report_rpc("weekly_report", access_token, week_offset)


def call_weekly_report_daily_rpc(access_token: str, week_offset: int) -> list[dict]:
    return _call_report_rpc("weekly_report_daily", access_token, week_offset)


def call_weekly_report_by_app_rpc(access_token: str, week_offset: int) -> list[dict]:
    return _call_report_rpc("weekly_report_by_app", access_token, week_offset)


def get_weekly_report_rows(
    creds: HTTPAuthorizationCredentials = Depends(security),
    week_offset: int = Query(0, le=0),
) -> list[dict]:
    """테스트에서 app.dependency_overrides로 교체하기 위한 진입점(ADR-010 get_jwks_client와 같은 패턴)."""
    try:
        return call_weekly_report_rpc(creds.credentials, week_offset)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"report query failed: {e}")


def get_weekly_report_daily_rows(
    creds: HTTPAuthorizationCredentials = Depends(security),
    week_offset: int = Query(0, le=0),
) -> list[dict]:
    try:
        return call_weekly_report_daily_rpc(creds.credentials, week_offset)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"daily report query failed: {e}")


def get_weekly_report_by_app_rows(
    creds: HTTPAuthorizationCredentials = Depends(security),
    week_offset: int = Query(0, le=0),
) -> list[dict]:
    try:
        return call_weekly_report_by_app_rpc(creds.credentials, week_offset)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"by-app report query failed: {e}")


@app.get("/reports/weekly")
def weekly_report(
    user_id: str = Depends(get_current_user_id),
    rows: list[dict] = Depends(get_weekly_report_rows),
    daily_rows: list[dict] = Depends(get_weekly_report_daily_rows),
    by_app_rows: list[dict] = Depends(get_weekly_report_by_app_rows),
):
    totals = {row["week"]: row["total_minutes"] for row in rows}
    last_week = totals.get("지난주", 0)
    this_week = totals.get("이번주", 0)
    days_compared = max((row.get("days_compared", 7) for row in rows), default=7)

    if days_compared == 0:
        change_pct = None
        message = "이번주가 막 시작됐어요. 내일부터 지난주와 비교해드릴게요."
    elif last_week == 0:
        change_pct = None
        message = "지난주 사용 기록이 없어요. 이번주부터 시작해봐요!"
    else:
        change_pct = round((this_week - last_week) / last_week * 100, 1)
        if change_pct == 0:
            message = "지난주랑 똑같아요. 변화를 줘볼까요?"
        elif change_pct < 0:
            message = f"지난주보다 {abs(change_pct)}% 줄였어요!"
        else:
            message = f"지난주보다 {change_pct}% 늘었어요. 다음주엔 목표를 다시 세워봐요."

    return {
        "last_week_minutes": last_week,
        "this_week_minutes": this_week,
        "change_pct": change_pct,
        "days_compared": days_compared,
        "message": message,
        "daily": [
            {
                "week": row["week"],
                "date": row["usage_date"],
                "minutes": row["total_minutes"],
            }
            for row in daily_rows
        ],
        "by_app": [
            {"app_name": row["app_name"], "minutes": row["total_minutes"]}
            for row in by_app_rows
        ],
    }
