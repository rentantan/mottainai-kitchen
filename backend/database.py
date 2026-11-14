"""SQLite connection and schema migrations."""
from __future__ import annotations

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from config import DATABASE_PATH


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


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    """Saved (favourite) recipes, so a dish can be cooked again without asking Gemini."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS saved_recipes (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            recipe_json TEXT NOT NULL,
            saved_at TEXT NOT NULL,
            UNIQUE (user_id, name)
        )
        """
    )

def _migrate_to_v3(connection: sqlite3.Connection) -> None:
    """How often / when a saved recipe was cooked (counted by "作った！")."""
    connection.execute("ALTER TABLE saved_recipes ADD COLUMN cooked_count INTEGER NOT NULL DEFAULT 0")
    connection.execute("ALTER TABLE saved_recipes ADD COLUMN last_cooked_at TEXT")


# Schema changes, oldest first. PRAGMA user_version records how many have been applied, so each
# runs once per database. To change the schema, append a function here; never edit an old one.
MIGRATIONS: list[Callable[[sqlite3.Connection], None]] = [_migrate_to_v1, _migrate_to_v2, _migrate_to_v3]


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
