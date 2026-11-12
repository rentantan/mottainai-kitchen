from __future__ import annotations

import re
import secrets
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Request

from database import db_connection, _current_user, _password_hash, _token_hash, _verify_password, _ensure_user_state
from models import AccountDelete, AuthCredentials, AuthSession, PasswordChange

router = APIRouter(prefix="/api/auth")

SESSION_SECONDS = 60 * 60 * 24 * 30

# Brute-force guard (in memory; resets on restart, enough for a single process).
# Failures are counted per email+IP, so a stranger cannot lock someone out just by
# typing their address. A looser per-email cap still stops attacks spread across many
# IPs, and a per-IP cap stops one client trying many addresses. Campus networks share
# one IP among many students, so the per-IP numbers are deliberately generous.
LOGIN_FAILURE_WINDOW_SECONDS = 15 * 60
MAX_LOGIN_FAILURES = 5            # same email from the same IP
MAX_LOGIN_FAILURES_PER_EMAIL = 20  # same email from any IP
MAX_LOGIN_FAILURES_PER_IP = 50     # any email from the same IP
REGISTER_WINDOW_SECONDS = 60 * 60
MAX_REGISTRATIONS_PER_IP = 20
_login_failures: dict[str, list[float]] = {}
_registrations: dict[str, list[float]] = {}

# Verifying against a throwaway hash when the email is unknown keeps the response
# time the same, so timing does not reveal which addresses have accounts.
_DUMMY_HASH = _password_hash(secrets.token_hex(16))


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _recent(store: dict[str, list[float]], key: str, now: float, window: float) -> list[float]:
    recent = [stamp for stamp in store.get(key, []) if now - stamp < window]
    if recent:
        store[key] = recent
    else:
        store.pop(key, None)
    return recent


def _login_keys(email: str, ip: str) -> list[tuple[str, int]]:
    return [(f"pair:{email}|{ip}", MAX_LOGIN_FAILURES), (f"email:{email}", MAX_LOGIN_FAILURES_PER_EMAIL),
            (f"ip:{ip}", MAX_LOGIN_FAILURES_PER_IP)]


def _clear_login_failures() -> None:
    _login_failures.clear()
    _registrations.clear()


@router.post("/register", response_model=AuthSession)
def register(payload: AuthCredentials, request: Request) -> dict[str, str]:
    email = payload.email.strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="有効なメールアドレスを入力してください")
    ip, now = _client_ip(request), time.time()
    if len(_recent(_registrations, ip, now, REGISTER_WINDOW_SECONDS)) >= MAX_REGISTRATIONS_PER_IP:
        raise HTTPException(status_code=429, detail="新規登録が集中しています。しばらく待ってから再試行してください。")
    with db_connection() as connection:
        if connection.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="このメールアドレスは既に登録されています")
        user_id = str(uuid.uuid4())
        connection.execute(
            "INSERT INTO users (id, email, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (user_id, email, _password_hash(payload.password), datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()),
        )
        if connection.execute("SELECT COUNT(*) AS count FROM users").fetchone()["count"] == 1:
            # Hand pre-login (legacy) data to the first account. This must run before
            # _ensure_user_state, otherwise the unique index on app_state.user_id fails.
            connection.execute("UPDATE pantry_items SET user_id = ? WHERE user_id IS NULL", (user_id,))
            connection.execute("UPDATE app_state SET user_id = ? WHERE id = 1 AND user_id IS NULL", (user_id,))
        _ensure_user_state(connection, user_id)
    _registrations.setdefault(ip, []).append(now)
    return _create_session(user_id, email)


@router.post("/login", response_model=AuthSession)
def login(payload: AuthCredentials, request: Request) -> dict[str, str]:
    email = payload.email.strip().lower()
    ip, now = _client_ip(request), time.time()
    keys = _login_keys(email, ip)
    for key, limit in keys:
        failures = _recent(_login_failures, key, now, LOGIN_FAILURE_WINDOW_SECONDS)
        if len(failures) >= limit:
            wait_minutes = max(1, round((LOGIN_FAILURE_WINDOW_SECONDS - (now - failures[0])) / 60))
            raise HTTPException(status_code=429, detail=f"ログインの失敗が続いたため一時的にロックしています。約{wait_minutes}分後に再試行してください。")
    with db_connection() as connection:
        user = connection.execute(
            "SELECT id, email, password_hash FROM users WHERE email = ?", (email,)
        ).fetchone()
    valid = _verify_password(payload.password, user["password_hash"] if user else _DUMMY_HASH)
    if user is None or not valid:
        for key, _ in keys:
            _login_failures.setdefault(key, []).append(now)
        raise HTTPException(status_code=401, detail="メールアドレスまたはパスワードが違います")
    _login_failures.pop(keys[0][0], None)
    _login_failures.pop(keys[1][0], None)
    return _create_session(user["id"], user["email"])


def _create_session(user_id: str, email: str) -> dict[str, str]:
    token = secrets.token_urlsafe(32)
    now = time.time()
    with db_connection() as connection:
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (now,))
        connection.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (_token_hash(token), user_id, now + SESSION_SECONDS),
        )
    return {"token": token, "email": email}


def _bearer_token(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    return authorization[7:].strip() if authorization.startswith("Bearer ") else ""


def _require_password(user_id: str, password: str) -> None:
    with db_connection() as connection:
        row = connection.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,)).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=403, detail="現在のパスワードが違います")


@router.get("/me", response_model=AuthSession)
def get_current_session(request: Request) -> dict[str, str]:
    user = _current_user(request)
    return {"token": "", "email": user["email"]}


@router.post("/logout")
def logout(request: Request) -> dict[str, bool]:
    token = _bearer_token(request)
    if token:
        with db_connection() as connection:
            connection.execute("DELETE FROM auth_sessions WHERE token_hash = ?", (_token_hash(token),))
    return {"loggedOut": True}


@router.post("/logout-others")
def logout_other_devices(request: Request) -> dict[str, int]:
    """End every session of this account except the one making the request (lost phone, shared PC)."""
    user = _current_user(request)
    with db_connection() as connection:
        removed = connection.execute(
            "DELETE FROM auth_sessions WHERE user_id = ? AND token_hash != ?", (user["id"], _token_hash(_bearer_token(request)))
        ).rowcount
    return {"loggedOut": removed}


@router.post("/password")
def change_password(payload: PasswordChange, request: Request) -> dict[str, bool]:
    """Change the password. Other devices are logged out; this one stays logged in."""
    user = _current_user(request)
    _require_password(user["id"], payload.currentPassword)
    with db_connection() as connection:
        connection.execute("UPDATE users SET password_hash = ? WHERE id = ?", (_password_hash(payload.newPassword), user["id"]))
        connection.execute(
            "DELETE FROM auth_sessions WHERE user_id = ? AND token_hash != ?", (user["id"], _token_hash(_bearer_token(request)))
        )
    return {"changed": True}


# Every table holding per-user rows. Deleted explicitly because older tables were
# created without ON DELETE CASCADE.
_USER_TABLES = ("pantry_items", "app_state", "recipe_suggestion_cache", "shopping_items", "pantry_staples",
                "waste_log", "consume_log", "gemini_user_daily_usage", "auth_sessions")


@router.delete("/account")
def delete_account(payload: AccountDelete, request: Request) -> dict[str, bool]:
    """Delete the account and all of its data. Requires the password."""
    user = _current_user(request)
    _require_password(user["id"], payload.password)
    with db_connection() as connection:
        for table in _USER_TABLES:
            connection.execute(f"DELETE FROM {table} WHERE user_id = ?", (user["id"],))
        connection.execute("DELETE FROM users WHERE id = ?", (user["id"],))
    return {"deleted": True}
