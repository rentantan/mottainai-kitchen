from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from database import CurrentUser, db_connection
from models import SavedRecipeWrite

# Saved (favourite) recipes. Only the pantry-independent fields are stored; the frontend
# matches them against the current fridge each time, so a saved recipe never shows stale
# "冷蔵庫にある" marks. Using a saved recipe does not call Gemini.
router = APIRouter(prefix="/api/recipes/saved")

MAX_SAVED_RECIPES = 50


def _read_saved(connection, user_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT id, recipe_json, saved_at FROM saved_recipes WHERE user_id = ? ORDER BY saved_at DESC", (user_id,)
    ).fetchall()
    items = []
    for row in rows:
        try:
            recipe = json.loads(row["recipe_json"])
        except json.JSONDecodeError:
            continue
        items.append({"id": row["id"], "savedAt": row["saved_at"], "recipe": recipe})
    return items


@router.get("")
def list_saved(user: CurrentUser) -> dict[str, Any]:
    with db_connection() as connection:
        return {"items": _read_saved(connection, user["id"])}


@router.post("")
def save_recipe(payload: SavedRecipeWrite, user: CurrentUser) -> dict[str, Any]:
    """Save a recipe. Saving a dish with the same name again replaces it (no duplicates)."""
    recipe = payload.model_dump()
    recipe["name"] = recipe["name"].strip()
    if not recipe["name"]:
        raise HTTPException(status_code=400, detail="レシピ名を入力してください")
    # Line details up with ingredients so the "材料の目安" rows stay paired.
    recipe["ingredientDetails"] = recipe["ingredientDetails"][:len(recipe["ingredients"])]
    recipe_json = json.dumps(recipe, ensure_ascii=False)
    # Immediate: the cap check must see rows saved by a concurrent request.
    with db_connection(immediate=True) as connection:
        existing = connection.execute(
            "SELECT id FROM saved_recipes WHERE user_id = ? AND name = ?", (user["id"], recipe["name"])
        ).fetchone()
        if existing:
            connection.execute("UPDATE saved_recipes SET recipe_json = ? WHERE id = ?", (recipe_json, existing["id"]))
            saved_id = existing["id"]
        else:
            count = connection.execute(
                "SELECT COUNT(*) AS c FROM saved_recipes WHERE user_id = ?", (user["id"],)
            ).fetchone()["c"]
            if count >= MAX_SAVED_RECIPES:
                raise HTTPException(status_code=400, detail=f"保存できるレシピは{MAX_SAVED_RECIPES}件までです。使わないものを外してください")
            saved_id = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO saved_recipes (id, user_id, name, recipe_json, saved_at) VALUES (?, ?, ?, ?, ?)",
                (saved_id, user["id"], recipe["name"], recipe_json, datetime.now(ZoneInfo("Asia/Tokyo")).isoformat()),
            )
        return {"items": _read_saved(connection, user["id"]), "id": saved_id}


@router.delete("/{saved_id}")
def delete_saved(saved_id: str, user: CurrentUser) -> dict[str, Any]:
    with db_connection() as connection:
        connection.execute("DELETE FROM saved_recipes WHERE id = ? AND user_id = ?", (saved_id, user["id"]))
        return {"items": _read_saved(connection, user["id"])}
