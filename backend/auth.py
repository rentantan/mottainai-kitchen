from __future__ import annotations

import re
import secrets
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

from database import db_connection, _current_user, _password_hash, _token_hash, _verify_password, _ensure_user_state
from models import AuthCredentials, AuthSession

router = APIRouter(prefix="/api/auth")

@router.post("/register", response_model=AuthSession)
def register(payload: AuthCredentials) -> dict[str, str]:
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="有効なメールアドレスを入力してください")
    with db_connection() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="このメールアドレスは既に登録されています")
        user_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, _password_hash(payload.password), datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()),
        )
        _ensure_user_state(connection, user_id)
        if connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"] == 1:
            connection.execute("UPDATE pantry_items SET user_id = ? WHERE user_id IS NULL", (user_id,))
            connection.execute("UPDATE app_state SET user_id = ? WHERE id = 1 AND user_id IS NULL", (user_id,))
    return _create_session(user_id, email)


@router.post("/login", response_model=AuthSession)
def login(payload: AuthCredentials) -> dict[str, str]:
    email = payload.email.strip().lower()
    with db_connection() as connection:
        user = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    if user is None or not _verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが違います")
    return _create_session(user["id"], user["email"])


def _create_session(user_id: str, email: str) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    with db_connection() as connection:
        connection.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, time.time() + 60 * 60 * 24 * 30),
        )
    return {"token": token, "email": email}


@router.get("/me", response_model=AuthSession)
def get_current_session(request: Request) -> dict[str, str]:
    user = _current_user(request)
    return {"token": "", "email": user["email"]}


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        with db_connection() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(authorization[7:].strip()),))
    return {"loggedOut": True}


