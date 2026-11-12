from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, HTTPException, Request

from database import (_current_user, _db_item_to_api, _ensure_user_state, _insert_pantry_item,
                      _read_pantry_state, _read_waste, db_connection, item_value_yen)
from models import BatchConsumeRequest, ConsumeRequest, PantryItemWrite, RestoreRequest, UndoConsumeRequest

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
def reset_pantry(request: Request, payload: list[PantryItemWrite] = Body(max_length=200),
                 keep_records: bool = False) -> dict[str, Any]:
    """Replace all pantry items. keep_records=true leaves the use-up count and waste log alone."""
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        connection.execute("DELETE FROM pantry_items WHERE user_id = ?", (user["id"],))
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
        if not keep_records:
            connection.execute("UPDATE app_state SET consumed_count = 0 WHERE user_id = ?", (user["id"],))
            connection.execute("DELETE FROM waste_log WHERE user_id = ?", (user["id"],))
            connection.execute("DELETE FROM consume_log WHERE user_id = ?", (user["id"],))
        for item in payload:
            _insert_pantry_item(connection, item, user["id"])
        return _read_pantry_state(connection, user["id"])


@router.post("/restore")
def restore_pantry_item(payload: RestoreRequest, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        item = _insert_pantry_item(connection, payload.item, user["id"], payload.createdAt)
        if payload.wasteId:
            connection.execute("DELETE FROM waste_log WHERE id = ? AND user_id = ?", (payload.wasteId, user["id"]))
        return {"item": item, "waste": _read_waste(connection, user["id"])}


@router.post("/consume-batch")
def consume_batch(payload: BatchConsumeRequest, request: Request) -> dict[str, Any]:
    """Consume several pantry items at once (e.g. after cooking a recipe). All-or-nothing."""
    user = _current_user(request)
    with db_connection() as connection:
        _ensure_user_state(connection, user["id"])
        log_ids = [_consume(connection, user["id"], entry.id, entry.amount)[1] for entry in payload.items]
        return {**_read_pantry_state(connection, user["id"]), "logIds": log_ids}


@router.post("/undo-consume")
def undo_consume(payload: UndoConsumeRequest, request: Request) -> dict[str, Any]:
    """Undo "使った" / "作った！": give the amount back, or bring back an item that was used up. All-or-nothing."""
    user = _current_user(request)
    with db_connection() as connection:
        for entry in payload.entries:
            log = connection.execute("SELECT * FROM consume_log WHERE id = ? AND user_id = ?", (entry.logId, user["id"])).fetchone()
            if log is None:
                raise HTTPException(status_code=404, detail="取り消せる記録が見つかりません")
            restored = connection.execute(
                "UPDATE pantry_items SET quantity = round(quantity + ?, 3) WHERE id = ? AND user_id = ?",
                (log["amount"], log["item_id"], user["id"]),
            ).rowcount
            if not restored:
                if entry.item is None:
                    raise HTTPException(status_code=400, detail="使い切った食材を戻すには食材の情報が必要です")
                _insert_pantry_item(connection, entry.item, user["id"], entry.createdAt)
            if log["used_up"]:
                connection.execute(
                    "UPDATE app_state SET consumed_count = MAX(consumed_count - 1, 0) WHERE user_id = ?", (user["id"],)
                )
            connection.execute("DELETE FROM consume_log WHERE id = ?", (entry.logId,))
        return _read_pantry_state(connection, user["id"])


@router.put("/{item_id}")
def update_pantry_item(item_id: str, payload: PantryItemWrite, request: Request) -> dict[str, Any]:
    user = _current_user(request)
    with db_connection() as connection:
        # purchased_quantity only grows: editing the remaining amount down must not
        # change what the price was paid for.
        result = connection.execute(
            """UPDATE pantry_items
               SET name = ?, quantity = ?, unit = ?, expiry_date = ?, category = ?, emoji = ?, note = ?,
                   frozen = ?, price_yen = ?,
                   purchased_quantity = MAX(COALESCE(purchased_quantity, 0), ?, COALESCE(?, 0))
               WHERE id = ? AND user_id = ?""",
            (payload.name.strip(), payload.quantity, payload.unit, payload.expiryDate.isoformat(),
             payload.category, payload.emoji, payload.note, int(payload.frozen), payload.priceYen,
             payload.quantity, payload.purchasedQuantity, item_id, user["id"]),
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
        row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        return _db_item_to_api(row)


@router.delete("/{item_id}")
def delete_pantry_item(item_id: str, request: Request, reason: Literal["removed", "discarded"] = "removed") -> dict[str, Any]:
    """reason=discarded records the item in the waste log ("もったいない記録"); removed just deletes it."""
    user = _current_user(request)
    with db_connection() as connection:
        row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"])).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="食材が見つかりません")
        connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user["id"]))
        connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user["id"],))
        waste_id = None
        if reason == "discarded":
            waste_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO waste_log (id, user_id, name, quantity, unit, category, emoji, expiry_date, discarded_at, value_yen)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (waste_id, user["id"], row["name"], row["quantity"], row["unit"], row["category"], row["emoji"],
                 row["expiry_date"], datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(), item_value_yen(row)),
            )
        return {"deleted": True, "item": _db_item_to_api(row), "wasteId": waste_id, "waste": _read_waste(connection, user["id"])}


@router.post("/{item_id}/consume")
def consume_pantry_item(item_id: str, request: Request, payload: ConsumeRequest | None = None) -> dict[str, Any]:
    user = _current_user(request)
    amount = payload.amount if payload and payload.amount is not None else 1.0
    with db_connection() as connection:
        updated_item, log_id = _consume(connection, user["id"], item_id, amount)
        state = connection.execute("SELECT consumed_count FROM app_state WHERE user_id = ?", (user["id"],)).fetchone()
        return {"item": updated_item, "consumedCount": int(state["consumed_count"]) if state else 0,
                "logId": log_id, "waste": _read_waste(connection, user["id"])}


def _consume(connection: sqlite3.Connection, user_id: str, item_id: str, amount: float) -> tuple[dict[str, Any] | None, str]:
    """Subtract `amount` from an item and log it.

    Returns (updated item or None if it was used up, consume_log id for undo).
    """
    row = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="食材が見つかりません")
    used = min(amount, float(row["quantity"]))
    remaining = round(float(row["quantity"]) - used, 3)
    used_up = remaining <= _EPSILON
    log_id = str(uuid.uuid4())
    connection.execute(
        "INSERT INTO consume_log (id, user_id, item_id, name, amount, used_up, consumed_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (log_id, user_id, item_id, row["name"], used, int(used_up), datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()),
    )
    if used_up:
        connection.execute("DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id))
        connection.execute(
            "UPDATE app_state SET consumed_count = consumed_count + 1, initialized = 1 WHERE user_id = ?", (user_id,)
        )
        return None, log_id
    connection.execute("UPDATE pantry_items SET quantity = ? WHERE id = ? AND user_id = ?", (remaining, item_id, user_id))
    connection.execute("UPDATE app_state SET initialized = 1 WHERE user_id = ?", (user_id,))
    updated = connection.execute("SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)).fetchone()
    return _db_item_to_api(updated), log_id
