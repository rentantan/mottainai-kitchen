"""Schema versioning: PRAGMA user_version tracks which MIGRATIONS have run."""
import sqlite3

import pytest

import database


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "migrate.db"
    monkeypatch.setattr(database, "DATABASE_PATH", str(path))
    return path


def _version(path):
    with sqlite3.connect(path) as connection:
        return connection.execute("PRAGMA user_version").fetchone()[0]


def _columns(path, table):
    with sqlite3.connect(path) as connection:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}


def test_fresh_database_gets_latest_version(db_path):
    database.init_database()
    assert _version(db_path) == len(database.MIGRATIONS)
    database.init_database()  # restarting is a no-op
    assert _version(db_path) == len(database.MIGRATIONS)


def test_unversioned_legacy_database_is_upgraded_and_keeps_data(db_path):
    """A database from before versioning (user_version 0, old pantry table) is brought up to date."""
    with sqlite3.connect(db_path) as connection:
        connection.execute("""CREATE TABLE pantry_items (id TEXT PRIMARY KEY, name TEXT NOT NULL,
            quantity REAL NOT NULL CHECK(quantity > 0), unit TEXT NOT NULL, expiry_date TEXT NOT NULL,
            category TEXT NOT NULL, emoji TEXT NOT NULL, note TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)""")
        connection.execute("INSERT INTO pantry_items VALUES ('a', '卵', 2, '個', '2026-01-01', 'その他', '🥚', '', '2026-01-01')")
    database.init_database()
    assert _version(db_path) == len(database.MIGRATIONS)
    assert {"user_id", "frozen", "price_yen", "purchased_quantity"} <= _columns(db_path, "pantry_items")
    with sqlite3.connect(db_path) as connection:
        assert connection.execute("SELECT name, frozen FROM pantry_items").fetchall() == [("卵", 0)]


def test_failed_migration_rolls_back(db_path, monkeypatch):
    database.init_database()

    def broken(connection):
        connection.execute("CREATE TABLE half_done (id INTEGER)")
        raise RuntimeError("boom")

    monkeypatch.setattr(database, "MIGRATIONS", [*database.MIGRATIONS, broken])
    with pytest.raises(RuntimeError):
        database.init_database()
    assert _version(db_path) == len(database.MIGRATIONS) - 1
    assert "id" not in _columns(db_path, "half_done")


def test_newer_database_is_refused(db_path):
    database.init_database()
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {len(database.MIGRATIONS) + 1}")
    with pytest.raises(RuntimeError, match="より新しい"):
        database.init_database()
