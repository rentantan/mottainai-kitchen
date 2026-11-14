"""Data access shared by several routers (pantry rows, waste summary, staples, per-user state)."""
from __future__ import annotations

import sqlite3
import uuid
from typing import Any

from clock import now_japan, now_japan_iso
from models import PantryItemWrite


def item_to_api(row: sqlite3.Row) -> dict[str, Any]:
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


def read_pantry_state(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    rows = connection.execute(
        "SELECT * FROM pantry_items WHERE user_id = ? ORDER BY expiry_date ASC, created_at DESC", (user_id,)
    ).fetchall()
    state = connection.execute(
        "SELECT consumed_count, initialized FROM app_state WHERE user_id = ?", (user_id,)
    ).fetchone()
    return {
        "items": [item_to_api(row) for row in rows],
        "consumedCount": int(state["consumed_count"] if state else 0),
        "initialized": bool(state["initialized"] if state else False),
        "waste": read_waste(connection, user_id),
    }


WASTE_RECENT_LIMIT = 20


def read_waste(connection: sqlite3.Connection, user_id: str) -> dict[str, Any]:
    """Discarded-food summary: the most recent entries plus all-time and this-month counts."""
    rows = connection.execute(
        "SELECT * FROM waste_log WHERE user_id = ? ORDER BY discarded_at DESC LIMIT ?", (user_id, WASTE_RECENT_LIMIT)
    ).fetchall()
    month_prefix = now_japan().strftime("%Y-%m")
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


def insert_pantry_item(connection: sqlite3.Connection, item: PantryItemWrite, user_id: str,
                        created_at: str | None = None) -> dict[str, Any]:
    item_id = str(uuid.uuid4())
    created_at = created_at or now_japan_iso()
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
    return item_to_api(row)


def read_staples(connection: sqlite3.Connection, user_id: str) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM pantry_staples WHERE user_id = ? ORDER BY name", (user_id,)
    ).fetchall()
    return [row["name"] for row in rows]


def ensure_user_state(connection: sqlite3.Connection, user_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO app_state (id, consumed_count, initialized, user_id) "
        "VALUES ((SELECT COALESCE(MAX(id), 0) + 1 FROM app_state), 0, 0, ?)",
        (user_id,),
    )
