from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from database import (_current_user, _db_item_to_api, _ensure_user_state, _insert_pantry_item,
                      _read_pantry_state, db_connection)
from models import BatchConsumeRequest, ConsumeRequest, PantryItemWrite

router = APIRouter(prefix="/api/pantry")

# Quantities are stored as REAL; treat anything this small as "used up".
_EPSILON = 1e-6


@router.get("")
def get_pantry(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        return _read_pantry_state(connection, user["id"])


@router.post("")
def create_pantry_item(payload: PantryItemWrite, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        return _insert_pantry_item(connection, payload, user["id"])


@router.put("/reset")
def reset_pantry(request: Request, payload: list[PantryItemWrite] = Body(max_length=200)) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        connection.execute("DELETE FROM pantry_items WHERE user_id = ?", (user["id"],))
        connection.execute("UPDATE app_state SET consumed_count = 0, initialized = 1 WHERE user_id = ?", (user["id"],))
        for item in payload:
            _insert_pantry_item(connection, item, user["id"])
        return _read_pantry_state(connection, user["id"])


@router.post("/consume-batch")
def consume_batch(payload: BatchConsumeRequest, request: Request) -> dict[str, Any]:
    """Consume several pantry items at once (e.g. after cooking a recipe). All-or-nothing."""
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        for entry in payload.items:
            _consume(connection, user["id"], entry.id, entry.amount)
        return _read_pantry_state(connection, user["id"])


@router.put("/{item_id}")
def update_pantry_item(item_id: str, payload: PantryItemWrite, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        result = connection.execute(
            """UPDATE pantry_items
               SET name = ?, quantity = ?, unit = ?, expiry_date = ?, category = ?, emoji = ?, note = ?
               WHERE id = ? AND user_id = ?""",
            (payload.name.strip(), payload.quantity, payload.unit, payload.expiryDate.isoformat(),
             payload.category, payload.emoji, payload.note, item_id, user["id"]),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
        row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        return _db_item_to_api(row)


@router.delete("/{item_id}")
def delete_pantry_item(item_id: str, request: Request) -> dict[str, bool]:
    user = _current_user(request)
    with db_connection() as connection:
        result = connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
    return {"deleted": True}


@router.post("/{item_id}/consume")
def consume_pantry_item(item_id: str, request: Request, payload: ConsumeRequest | None = None) -> dict[str, Any]:
    user = _current_user(request)
    amount = payload.amount if payload and payload.amount is not None else 1.0
    with db_connection() as connection:
        updated_item = _consume(connection, user["id"], item_id, amount)
        state = connection.execute("SELECT consumed_count FROM app_state WHERE user_id = ?", (user["id"],)).fetchone()
        return {"item": updated_item, "consumedCount": int(state["consumed_count"]) if state else 0}


def _consume(connection: sqlite3.Connection, user_id: str, item_id: str, amount: float) -> dict[str, Any] | None:
    """Subtract `amount` from an item. Returns the updated item, or None if it was used up."""
    row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="食材が見つかりません")
    remaining = round(float(row["quantity"]) - amount, 3)
    if remaining <= _EPSILON:
        connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id))
        connection.execute(
            "UPDATE app_state SET consumed_count = consumed_count + 1, initialized = 1 WHERE user_id = ?", (user_id,)
        )
        return None
    connection.execute("UPDATE pantry_items SET quantity = ? WHERE id = ? AND user_id = ?", (remaining, item_id, user_id))
    connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user_id,))
    updated = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
    return _db_item_to_api(updated)
