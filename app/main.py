import os

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import create_engine, text
from supabase import create_client

load_dotenv()

app = FastAPI(title="peTox API")

engine = create_engine(os.environ["DATABASE_URL"])
supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])


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
