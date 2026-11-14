from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from database import CurrentUser, _ensure_user_state, _insert_pantry_item, _read_staples, db_connection
from ingredients import matches_name
from models import ShoppingItemCreate, ShoppingItemUpdate, StaplesWrite, StockFromShoppingRequest

router = APIRouter(prefix="/api")

MAX_SHOPPING_ITEMS = 200


def _clean_names(names: list[str], limit: int) -> list[str]:
    """Trim, drop blanks and de-duplicate while keeping order."""
    cleaned = (name.strip()[:limit] for name in names if isinstance(name, str))
    return list(dict.fromkeys(name for name in cleaned if name))


def _read_shopping(connection, user_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT id, name, checked, created_at FROM shopping_items WHERE user_id = ? ORDER BY checked ASC, created_at DESC",
        (user_id,),
    ).fetchall()
    return [{"id": row["id"], "name": row["name"], "checked": bool(row["checked"]), "createdAt": row["created_at"]} for row in rows]


@router.get("/shopping")
def list_shopping(user: CurrentUser) -> dict[str, Any]:
    with db_connection() as connection:
        return {"items": _read_shopping(connection, user["id"])}


RESTOCK_DAYS = 30
MAX_RESTOCK_SUGGESTIONS = 8


@router.get("/shopping/restock")
def restock_suggestions(user: CurrentUser) -> dict[str, list[str]]:
    """Foods used up recently ("使い切った"), newest first, one name per food (卵 / たまご count
    once). The client hides the ones already in the fridge or on the list."""
    since = (datetime.now(ZoneInfo("Asia/Tokyo")) - timedelta(days=RESTOCK_DAYS)).isoformat()
    with db_connection() as connection:
        rows = connection.execute(
            "SELECT name FROM consume_log WHERE user_id = ? AND used_up = 1 AND consumed_at >= ? ORDER BY consumed_at DESC LIMIT 200",
            (user["id"], since),
        ).fetchall()
    names: list[str] = []
    for row in rows:
        if not any(matches_name(row["name"], other) for other in names):
            names.append(row["name"])
        if len(names) >= MAX_RESTOCK_SUGGESTIONS:
            break
    return {"names": names}


@router.post("/shopping")
def add_shopping(payload: ShoppingItemCreate, user: CurrentUser) -> dict[str, Any]:
    """Add names to the list. Names already on the list (unchecked) are skipped, including
    other spellings of the same food (ネギ / ねぎ / 長ねぎ, 醤油 / しょうゆ)."""
    names = _clean_names(payload.names, 60)
    # Immediate: the duplicate check and the 200-item cap must see the rows this request inserts.
    with db_connection(immediate=True) as connection:
        existing = {
            row["name"] for row in connection.execute(
                "SELECT name FROM shopping_items WHERE user_id = ? AND checked = 0", (user["id"],)
            )
        }
        count = connection.execute("SELECT COUNT(*) AS c FROM shopping_items WHERE user_id = ?", (user["id"],)).fetchone()["c"]
        new_names: list[str] = []
        for name in names:
            if not any(matches_name(name, other) for other in [*existing, *new_names]):
                new_names.append(name)
        if count + len(new_names) > MAX_SHOPPING_ITEMS:
            raise HTTPException(status_code=400, detail=f"買い物リストは{MAX_SHOPPING_ITEMS}件までです")
        now = datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()
        for name in new_names:
            connection.execute(
                "INSERT INTO shopping_items (id, user_id, name, checked, created_at) VALUES (?, ?, ?, 0, ?)",
                (str(uuid.uuid4()), user["id"], name, now),
            )
        return {"items": _read_shopping(connection, user["id"]), "added": len(new_names)}


@router.patch("/shopping/{item_id}")
def update_shopping(item_id: str, payload: ShoppingItemUpdate, user: CurrentUser) -> dict[str, Any]:
    with db_connection() as connection:
        result = connection.execute(
            "UPDATE shopping_items SET checked = ? WHERE id = ? AND user_id = ?",
            (int(payload.checked), item_id, user["id"]),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="買い物リストの項目が見つかりません")
        return {"items": _read_shopping(connection, user["id"])}


@router.post("/shopping/stock")
def stock_from_shopping(payload: StockFromShoppingRequest, user: CurrentUser) -> dict[str, Any]:
    """Put bought items into the fridge and tick them off, in one transaction. Items ticked
    in the shop can be registered too; rows deleted meanwhile are skipped."""
    with db_connection(immediate=True) as connection:
        _ensure_user_state(connection, user["id"])
        added: list[dict[str, Any]] = []
        for entry in payload.entries:
            result = connection.execute(
                "UPDATE shopping_items SET checked = 1 WHERE id = ? AND user_id = ?",
                (entry.shoppingId, user["id"]),
            )
            if result.rowcount:
                added.append(_insert_pantry_item(connection, entry.item, user["id"]))
        return {"added": added, "items": _read_shopping(connection, user["id"])}


@router.delete("/shopping/checked")
def clear_checked_shopping(user: CurrentUser) -> dict[str, Any]:
    with db_connection() as connection:
        connection.execute("DELETE FROM shopping_items WHERE user_id = ? AND checked = 1", (user["id"],))
        return {"items": _read_shopping(connection, user["id"])}


@router.delete("/shopping/{item_id}")
def delete_shopping(item_id: str, user: CurrentUser) -> dict[str, Any]:
    with db_connection() as connection:
        connection.execute("DELETE FROM shopping_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        return {"items": _read_shopping(connection, user["id"])}


@router.get("/staples")
def get_staples(user: CurrentUser) -> dict[str, list[str]]:
    with db_connection() as connection:
        return {"names": _read_staples(connection, user["id"])}


@router.put("/staples")
def put_staples(payload: StaplesWrite, user: CurrentUser) -> dict[str, list[str]]:
    names = _clean_names(payload.names, 30)
    with db_connection() as connection:
        connection.execute("DELETE FROM pantry_staples WHERE user_id = ?", (user["id"],))
        connection.executemany(
            "INSERT INTO pantry_staples (user_id, name) VALUES (?, ?)", [(user["id"], name) for name in names]
        )
        return {"names": _read_staples(connection, user["id"])}
