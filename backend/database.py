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
from typing import Annotated, Any, Callable
from zoneinfo import ZoneInfo

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from config import DATABASE_PATH
from models import PantryItemWrite

@contextmanager
def db_connection(immediate: bool = False):
    """Open a short-lived SQLite connection and commit successful writes.

    immediate=True takes the write lock up front (BEGIN IMMEDIATE). Use it for
    read-then-write handlers (e.g. "使った": read the quantity, then store the new one) so
    two concurrent requests (two tabs, phone + PC) cannot both read the old value and
    overwrite each other's change.
    """
    db_path = Path(DATABASE_PATH)
    if str(DATABASE_PATH) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(DATABASE_PATH), timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    if immediate:
        connection.execute("BEGIN IMMEDIATE")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _migrate_to_v1(connection: sqlite3.Connection) -> None:
    """Baseline schema (everything up to app v2.4).

    Written to be idempotent (CREATE IF NOT EXISTS, add-column-if-missing) because databases
    made before schema versioning start at user_version 0 and may already hold any part of it.
    """
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
    if "frozen" not in pantry_columns:
        connection.execute("ALTER TABLE pantry_items ADD COLUMN frozen INTEGER NOT NULL DEFAULT 0")
    if "price_yen" not in pantry_columns:
        connection.execute("ALTER TABLE pantry_items ADD COLUMN price_yen INTEGER")
    if "purchased_quantity" not in pantry_columns:
        connection.execute("ALTER TABLE pantry_items ADD COLUMN purchased_quantity REAL")
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
    waste_columns = {row["name"] for row in connection.execute("PRAGMA table_info(waste_log)")}
    if "value_yen" not in waste_columns:
        connection.execute("ALTER TABLE waste_log ADD COLUMN value_yen INTEGER")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_waste_log_user_id ON waste_log(user_id, discarded_at)")
    # Every "使った" is logged so it can be undone and so this month's use-up rate can be shown.
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS consume_log (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            item_id TEXT NOT NULL,
            name TEXT NOT NULL,
            amount REAL NOT NULL,
            used_up INTEGER NOT NULL DEFAULT 0,
            consumed_at TEXT NOT NULL
        )
        """
    )
    connection.execute("CREATE INDEX IF NOT EXISTS idx_consume_log_user_id ON consume_log(user_id, consumed_at)")
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



# Schema changes, oldest first. PRAGMA user_version records how many have been applied, so each
# runs once per database. To change the schema, append a function here; never edit an old one.
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_migrate_to_v1]


def schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def init_database() -> None:
    with db_connection() as connection:
        connection.execute("PRAGMA journal_mode=WAL")  # outside the transaction: SQLite refuses it inside one
    with db_connection(immediate=True) as connection:
        # Immediate: two processes starting at once cannot both apply the same migration.
        current = schema_version(connection)
        if current > len(MIGRATIONS):
            raise RuntimeError(
                f"データベースのスキーマ（v{current}）がこのアプリ（v{len(MIGRATIONS)}）より新しいため起動できません。"
                "アプリを最新版に更新してください。")
        for version, migrate in enumerate(MIGRATIONS[current:], start=current + 1):
            migrate(connection)
            # Same transaction as the migration: a failure rolls back both.
            connection.execute(f"PRAGMA user_version = {version}")
        connection.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (time.time(),))

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
        "frozen": bool(row["frozen"]),
        "priceYen": row["price_yen"],
        "purchasedQuantity": row["purchased_quantity"],
    }


def item_value_yen(row: sqlite3.Row) -> int | None:
    """Yen value of what is left of an item: price × remaining / purchased quantity."""
    if row["price_yen"] is None:
        return None
    purchased = row["purchased_quantity"] or row["quantity"]
    return round(row["price_yen"] * min(1.0, row["quantity"] / purchased))


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
        "SELECT COUNT(*) AS total, SUM(CASE WHEN substr(discarded_at, 1, 7) = ? THEN 1 ELSE 0 END) AS month, "
        "COALESCE(SUM(value_yen), 0) AS total_yen, "
        "COALESCE(SUM(CASE WHEN substr(discarded_at, 1, 7) = ? THEN value_yen ELSE 0 END), 0) AS month_yen "
        "FROM waste_log WHERE user_id = ?",
        (month_prefix, month_prefix, user_id),
    ).fetchone()
    used_up = connection.execute(
        "SELECT COUNT(*) AS month FROM consume_log WHERE user_id = ? AND used_up = 1 AND substr(consumed_at, 1, 7) = ?",
        (user_id, month_prefix),
    ).fetchone()
    return {
        "items": [{
            "id": row["id"], "name": row["name"], "quantity": row["quantity"], "unit": row["unit"],
            "category": row["category"], "emoji": row["emoji"], "expiryDate": row["expiry_date"],
            "discardedAt": row["discarded_at"], "valueYen": row["value_yen"],
        } for row in rows],
        "totalCount": int(counts["total"] or 0),
        "monthCount": int(counts["month"] or 0),
        "totalYen": int(counts["total_yen"] or 0),
        "monthYen": int(counts["month_yen"] or 0),
        # Items used up this month (from consume_log), for this month's use-up rate.
        "monthUsedUp": int(used_up["month"] or 0),
    }


def _insert_pantry_item(connection: sqlite3.Connection, item: PantryItemWrite, user_id: str,
                        created_at: str | None = None) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    created_at = created_at or datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
    connection.execute(
        """INSERT INTO pantry_items
           (id, name, quantity, unit, expiry_date, category, emoji, note, created_at, user_id,
            frozen, price_yen, purchased_quantity)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (item_id, item.name.strip(), item.quantity, item.unit, item.expiryDate.isoformat(),
         item.category, item.emoji, item.note, created_at, user_id,
         int(item.frozen), item.priceYen, max(item.purchasedQuantity or 0, item.quantity)),
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
            (_token_hash(token), time.time()),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="ログインの有効期限が切れています")
    return row


# Use as a handler parameter (`user: CurrentUser`) on every endpoint that needs a login.
CurrentUser = Annotated[sqlite3.Row, Depends(current_user)]


def _ensure_user_state(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO app_state (id, consumed_count, initialized, user_id) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM app_state), 0, 0, ?)",
        (user_id,),
    )

