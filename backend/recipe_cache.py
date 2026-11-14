"""SQLite cache of successful Gemini suggestions (same pantry + settings + Japan date → same result)."""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from clock import today_japan
from config import CACHE_SECONDS, GEMINI_MODEL, PROMPT_VERSION
from database import db_connection
from models import PantryInput, SuggestRequest

def cache_key(payload: SuggestRequest, pantry: list[PantryInput], user_id: str, staples: list[str]) -> str:
    """Same pantry + settings on the same Japan date reuse one AI result.

    refresh / exclude_recipe_names are deliberately excluded: a refresh overwrites this
    entry, so the next normal request shows the newest suggestions.
    """
    serializable = {
        "user_id": user_id,
        "pantry": sorted(
            [item.model_dump(mode="json") for item in pantry],
            key=lambda item: (item["name"], item["expiry_date"], item["quantity"], item["unit"]),
        ),
        "staples": sorted(staples),
        "preferences": payload.preferences.model_dump(mode="json"),
        "japan_date": today_japan().isoformat(),
        "model": GEMINI_MODEL,
        "prompt_version": PROMPT_VERSION,
    }
    raw = json.dumps(serializable, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def read_cache(cache_key: str) -> dict[str, Any] | None:
    now = time.time()
    with db_connection() as connection:
        row = connection.execute(
            "SELECT result_json, expires_at FROM recipe_suggestion_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        if float(row["expires_at"]) <= now:
            connection.execute("DELETE FROM recipe_suggestion_cache WHERE cache_key = ?", (cache_key,))
            return None
        try:
            result = json.loads(row["result_json"])
        except (TypeError, json.JSONDecodeError):
            connection.execute("DELETE FROM recipe_suggestion_cache WHERE cache_key = ?", (cache_key,))
            return None
    if not isinstance(result, dict):
        return None
    return {
        **result,
        "cached": True,
        "message": "同じ食材・予算・時間のAI提案をSQLiteキャッシュから再表示しています。Gemini APIへの新しいリクエストは送信していません。",
    }


def write_cache(cache_key: str, user_id: str, result: dict[str, Any]) -> None:
    now = time.time()
    with db_connection() as connection:
        connection.execute(
            """
            INSERT INTO recipe_suggestion_cache (cache_key, user_id, result_json, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(cache_key) DO UPDATE SET
                result_json = excluded.result_json,
                created_at = excluded.created_at,
                expires_at = excluded.expires_at
            """,
            (cache_key, user_id, json.dumps(result, ensure_ascii=False), now, now + CACHE_SECONDS),
        )
        # Keep only the most recent 100 cache records.
        connection.execute(
            "DELETE FROM recipe_suggestion_cache WHERE cache_key NOT IN "
            "(SELECT cache_key FROM recipe_suggestion_cache ORDER BY created_at DESC LIMIT 100)"
        )
