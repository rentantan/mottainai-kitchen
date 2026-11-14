"""Password and session-token hashing, and the logged-in-user dependency."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from database import db_connection


def hash_password(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 210_000)
    return f"{actual_salt.hex()}:{digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 210_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# auto_error=False: a missing token gets this app's Japanese 401 message, not FastAPI's default.
# Declared with Security so /docs shows the lock icon and an "Authorize" button.
_bearer_scheme = HTTPBearer(auto_error=False, description="ログイン・新規登録で受け取ったトークン")


def current_user(credentials: HTTPAuthorizationCredentials | None = Security(_bearer_scheme)) -> sqlite3.Row:
    """Dependency: the logged-in user (id, email). Raises 401 without a valid session."""
    token = credentials.credentials.strip() if credentials else ""
    if not token:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.email FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (hash_token(token), time.time()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="ログインの有効期限が切れています")
    return row


# Use as a handler parameter (`user: CurrentUser`) on every endpoint that needs a login.
CurrentUser = Annotated[sqlite3.Row, Depends(current_user)]
