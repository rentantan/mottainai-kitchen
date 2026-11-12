from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request

from config import DATABASE_PATH
from models import PantryItemWrite

@contextmanager
def db_connection():
    """Open a short-lived SQLite connection and commit successful writes."""
    db_path = Path(DATABASE_PATH)
    if str(DATABASE_PATH) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    with db_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                expires_at REAL NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
            """
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS pantry_items (
                id TEXT PRIMARY KEY, name TEXT NOT NULL,
                quantity REAL NOT NULL CHECK(quantity > 0), unit TEXT NOT NULL,
                expiry_date TEXT NOT NULL, category TEXT NOT NULL, emoji TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                user_id TEXT REFERENCES users(id)
            )"""
        )
        pantry_columns = {row["name"] for row in connection.execute("PRAGMA table_info(pantry_items)")}
        if "user_id" not in pantry_columns:
            connection.execute("ALTER TABLE pantry_items ADD COLUMN user_id TEXT REFERENCES users(id)")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS app_state (
                id INTEGER PRIMARY KEY,
                consumed_count INTEGER NOT NULL DEFAULT 0,
                initialized INTEGER NOT NULL DEFAULT 0,
                user_id TEXT REFERENCES users(id)
            )"""
        )
        state_schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'app_state'"
        ).fetchone()["sql"] or ""
        if "CHECK(id = 1)" in state_schema:
            connection.execute("ALTER TABLE app_state RENAME TO app_state_legacy")
            connection.execute(
                """CREATE TABLE app_state (
                    id INTEGER PRIMARY KEY,
                    consumed_count INTEGER NOT NULL DEFAULT 0,
                    initialized INTEGER NOT NULL DEFAULT 0,
                    user_id TEXT REFERENCES users(id)
                )"""
            )
            connection.execute(
                "INSERT INTO app_state (id, consumed_count, initialized, user_id) "
                "SELECT id, consumed_count, initialized, NULL FROM app_state_legacy"
            )
            connection.execute("DROP TABLE app_state_legacy")
        state_columns = {row["name"] for row in connection.execute("PRAGMA table_info(app_state)")}
        if "user_id" not in state_columns:
            connection.execute("ALTER TABLE app_state ADD COLUMN user_id TEXT REFERENCES users(id)")
        connection.execute("INSERT OR IGNORE INTO app_state (id, consumed_count, initialized, user_id) VALUES (1, 0, 0, NULL)")
        connection.execute(
            "DELETE FROM app_state WHERE user_id IS NOT NULL AND id NOT IN "
            "(SELECT MIN(id) FROM app_state WHERE user_id IS NOT NULL GROUP BY user_id)"
        )
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_app_state_user_id ON app_state(user_id) WHERE user_id IS NOT NULL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS recipe_suggestion_cache (
                cache_key TEXT PRIMARY KEY,
                user_id TEXT REFERENCES users(id),
                result_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        cache_columns = {row["name"] for row in connection.execute("PRAGMA table_info(recipe_suggestion_cache)")}
        if "user_id" not in cache_columns:
            connection.execute("ALTER TABLE recipe_suggestion_cache ADD COLUMN user_id TEXT REFERENCES users(id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_pantry_items_user_id ON pantry_items(user_id)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_recipe_cache_user_id ON recipe_suggestion_cache(user_id)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS shopping_items (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                checked INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_shopping_items_user_id ON shopping_items(user_id)")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS pantry_staples (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                PRIMARY KEY (user_id, name)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS waste_log (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                quantity REAL NOT NULL,
                unit TEXT NOT NULL,
                category TEXT NOT NULL,
                emoji TEXT NOT NULL,
                expiry_date TEXT NOT NULL,
                discarded_at TEXT NOT NULL
            )
            """
        )
        connection.execute("CREATE INDEX IF NOT EXISTS idx_waste_log_user_id ON waste_log(user_id, discarded_at)")
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (time.time(),))
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gemini_daily_usage (
                usage_date TEXT PRIMARY KEY,
                request_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS gemini_user_daily_usage (
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                usage_date TEXT NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, usage_date)
            )
            """
        )


def _db_item_to_api(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "name": row["name"],
        "quantity": row["quantity"],
        "unit": row["unit"],
        "expiryDate": row["expiry_date"],
        "category": row["category"],
        "emoji": row["emoji"],
        "note": row["note"],
        "createdAt": row["created_at"],
    }


def _read_pantry_state(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT * FROM pantry_items WHERE user_id = ? ORDER BY expiry_date ASC, created_at DESC", (user_id,)
    ).fetchall()
    state = connection.execute(
        "SELECT consumed_count, initialized FROM app_state WHERE user_id = ?", (user_id,)
    ).fetchone()
    return {
        "items": [_db_item_to_api(row) for row in rows],
        "consumedCount": int(state["consumed_count"] if state else 0),
        "initialized": bool(state["initialized"] if state else False),
        "waste": _read_waste(connection, user_id),
    }


WASTE_RECENT_LIMIT = 20


def _read_waste(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    """Discarded-food summary: the most recent entries plus all-time and this-month counts."""
    rows = connection.execute(
        "SELECT * FROM waste_log WHERE user_id = ? ORDER BY discarded_at DESC LIMIT ?", (user_id, WASTE_RECENT_LIMIT)
    ).fetchall()
    month_prefix = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m")
    counts = connection.execute(
        "SELECT COUNT(*) AS total, SUM(CASE WHEN substr(discarded_at, 1, 7) = ? THEN 1 ELSE 0 END) AS month "
        "FROM waste_log WHERE user_id = ?",
        (month_prefix, user_id),
    ).fetchone()
    return {
        "items": [{
            "id": row["id"], "name": row["name"], "quantity": row["quantity"], "unit": row["unit"],
            "category": row["category"], "emoji": row["emoji"], "expiryDate": row["expiry_date"],
            "discardedAt": row["discarded_at"],
        } for row in rows],
        "totalCount": int(counts["total"] or 0),
        "monthCount": int(counts["month"] or 0),
    }


def _insert_pantry_item(connection: sqlite3.Connection, item: PantryItemWrite, user_id: str,
                        created_at: str | None = None) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    created_at = created_at or datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    connection.execute(
        """INSERT INTO pantry_items
           (id, name, quantity, unit, expiry_date, category, emoji, note, created_at, user_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, item.name.strip(), item.quantity, item.unit, item.expiryDate.isoformat(),
         item.category, item.emoji, item.note, created_at, user_id),
    )
    connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user_id,))
    row = connection.execute("SELECT * FROM pantry_items WHERE id = ?", (item_id,)).fetchone()
    return _db_item_to_api(row)


def _read_staples(connection: sqlite3.Connection, user_id: str) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM pantry_staples WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    return [row["name"] for row in rows]


def _password_hash(password: str, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, 210_000)
    return f"{actual_salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split(":", 1)
        expected = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 210_000)
        return hmac.compare_digest(expected.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _current_user(request: Request) -> sqlite3.Row:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="ログインが必要です")
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="ログインが必要です")
    with db_connection() as connection:
        row = connection.execute(
            """
            SELECT users.id, users.email FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (_token_hash(token), time.time()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="ログインの有効期限が切れています")
    return row


def _ensure_user_state(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO app_state (id, consumed_count, initialized, user_id) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM app_state), 0, 0, ?)",
        (user_id,),
    )

