from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException, Request

from database import (_current_user, _db_item_to_api, _ensure_user_state, _insert_pantry_item,
                      _read_pantry_state, db_connection)
from models import PantryItemWrite

router = APIRouter(prefix="/api/pantry")

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
            from fastapi import HTTPException
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
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
    return {"deleted": True}


@router.post("/{item_id}/consume")
def consume_pantry_item(item_id: str, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        if row is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        if float(row["quantity"]) <= 1:
            connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
            connection.execute("UPDATE app_state SET consumed_count = consumed_count + 1, initialized = 1 WHERE user_id = ?", (user["id"],))
            updated_item = None
        else:
            connection.execute(
                "UPDATE pantry_items SET quantity = quantity - 1 WHERE id = ? AND user_id = ?", (item_id, user["id"])
            )
            connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
            updated = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
            updated_item = _db_item_to_api(updated)
        state = connection.execute("SELECT consumed_count FROM app_state WHERE user_id = ?", (user["id"],)).fetchone()
        return {"item": updated_item, "consumedCount": int(state["consumed_count"])}


