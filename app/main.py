import os

import jwt
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, text
from supabase import create_client

load_dotenv()

app = FastAPI(title="peTox API")

engine = create_engine(os.environ["DATABASE_URL"])
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


@app.get("/db-health")
def db_health():
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    return {"db": "ok"}


@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}


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
