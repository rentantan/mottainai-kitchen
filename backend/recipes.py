"""/api/recipes/suggest: Gemini suggestions with cache and limits, or the built-in recipes as a fallback."""
from __future__ import annotations

import hashlib
from datetime import date
from typing import Any

from fastapi import APIRouter

import gemini
import recipe_cache
import recipe_limits
from clock import today_japan
from config import GEMINI_API_KEY, GEMINI_MODEL
from database import db_connection
from ingredients import matches_name
from models import PantryInput, RecipePreferences, SuggestRequest
from recipe_fallbacks import FALLBACK_RECIPES
from security import CurrentUser
from store import read_staples

router = APIRouter(prefix="/api/recipes")


def matches_ingredient(required: str, pantry_item: PantryInput) -> bool:
    return matches_name(required, pantry_item.name)


def _is_available(ingredient: str, usable_pantry: list[PantryInput], staples: list[str]) -> bool:
    """In stock if a non-expired pantry item or a registered staple seasoning matches."""
    return (any(matches_ingredient(ingredient, item) for item in usable_pantry)
            or any(matches_name(ingredient, staple) for staple in staples))


# Points by days left (index 0 = today). Expired or 8+ days: no points. Same table as the frontend.
_EXPIRY_POINTS = (100, 80, 60, 40, 20, 15, 10, 5)


def expiry_priority_points(days_left: int) -> int:
    """Deterministic priority: nearest non-expired dates receive the most points."""
    return _EXPIRY_POINTS[days_left] if 0 <= days_left < len(_EXPIRY_POINTS) else 0


def _score(ingredients: list[str], usable_pantry: list[PantryInput], staples: list[str], today: date) -> dict[str, Any]:
    """Match a recipe's ingredients against the non-expired pantry and staples."""
    matched = [ingredient for ingredient in ingredients if _is_available(ingredient, usable_pantry, staples)]
    matched_items = [item for item in usable_pantry if any(matches_ingredient(ingredient, item) for ingredient in matched)]
    expiry_days = [(item.expiry_date - today).days for item in matched_items]
    return {
        "matchedIngredients": matched,
        "missingIngredients": [ingredient for ingredient in ingredients if ingredient not in matched],
        "usesExpiring": len({item.name for item in matched_items if 0 <= (item.expiry_date - today).days <= 3}),
        "nearestExpiryDays": min(expiry_days, default=999),
        "expiryPriorityScore": sum(expiry_priority_points(days) for days in expiry_days),
        "matchPercent": round(len(matched) / max(1, len(ingredients)) * 100),
    }


def _rank_key(row: dict[str, Any]) -> tuple:
    """Soonest-expiring food first, then more of it used, then fewer purchases, then cheaper and quicker."""
    return (row["nearestExpiryDays"], -row["expiryPriorityScore"], -row["usesExpiring"], -row["matchPercent"],
            row["estimatedCostYen"], row["minutes"])


def _safe_string(value: Any, fallback: str, limit: int = 160) -> str:
    if not isinstance(value, str):
        return fallback
    cleaned = value.strip()
    return cleaned[:limit] if cleaned else fallback


def _format_gemini_recipes(raw: dict[str, Any], pantry: list[PantryInput], staples: list[str]) -> list[dict[str, Any]]:
    today = today_japan()
    formatted: list[dict[str, Any]] = []
    # Only non-expired pantry items count as available or as expiry-priority ingredients.
    usable_pantry = [item for item in pantry if item.expiry_date >= today]
    expired_pantry = [item for item in pantry if item.expiry_date < today]
    raw_recipes = raw.get("recipes", [])

    for index, candidate in enumerate(raw_recipes[:3]):
        if not isinstance(candidate, dict):
            continue
        raw_ingredients = candidate.get("ingredients", [])
        ingredients = list(dict.fromkeys(
            str(value).strip()[:50]
            for value in raw_ingredients
            if isinstance(value, str) and value.strip()
        ))[:12] if isinstance(raw_ingredients, list) else []
        if not ingredients:
            continue

        details_raw = candidate.get("ingredientDetails", [])
        details = [str(value).strip()[:80] for value in details_raw if isinstance(value, str) and value.strip()] if isinstance(details_raw, list) else []
        if len(details) != len(ingredients):
            details = ingredients.copy()

        steps_raw = candidate.get("steps", [])
        steps = [str(value).strip()[:240] for value in steps_raw if isinstance(value, str) and value.strip()] if isinstance(steps_raw, list) else []
        if not steps:
            continue

        # Reject a suggestion that appears to use an expired pantry item, unless another
        # non-expired stock of the same ingredient is available.
        uses_expired_stock = any(
            any(matches_ingredient(ingredient, expired_item) for expired_item in expired_pantry)
            and not _is_available(ingredient, usable_pantry, staples)
            for ingredient in ingredients
        )
        if uses_expired_stock:
            continue

        try:
            minutes = max(1, min(90, int(candidate.get("minutes", 15))))
        except (TypeError, ValueError):
            minutes = 15
        try:
            estimated_cost = max(0, min(5000, int(candidate.get("estimatedCostYen", 300))))
        except (TypeError, ValueError):
            estimated_cost = 300

        formatted.append({
            "id": f"gemini-{index}-{hashlib.sha1(_safe_string(candidate.get('name'), 'recipe').encode()).hexdigest()[:8]}",
            "name": _safe_string(candidate.get("name"), "節約かんたんごはん", 60),
            "description": _safe_string(candidate.get("description"), "冷蔵庫の食材で作れる一品です。", 180),
            "minutes": minutes,
            "difficulty": candidate.get("difficulty") if candidate.get("difficulty") in ("かんたん", "ふつう") else "かんたん",
            "emoji": _safe_string(candidate.get("emoji"), "🍚", 8),
            "ingredients": ingredients,
            "ingredientDetails": details,
            "steps": steps[:8],
            **_score(ingredients, usable_pantry, staples, today),
            "estimatedCostYen": estimated_cost,
            "servings": 1,
            "source": "Gemini AI",
        })
    formatted.sort(key=_rank_key)
    return formatted


def _format_fallback(pantry: list[PantryInput], preferences: RecipePreferences, staples: list[str],
                     exclude_names: list[str] | None = None) -> list[dict[str, Any]]:
    today = today_japan()
    usable_pantry = [item for item in pantry if item.expiry_date >= today]
    recipes: list[dict[str, Any]] = []
    for recipe in FALLBACK_RECIPES:
        if preferences.equipment == "microwave" and not recipe.get("microwaveOnly"):
            continue
        if recipe["minutes"] > preferences.max_minutes:
            continue
        if recipe["estimatedCostYen"] > preferences.budget_yen:
            continue
        recipes.append({
            **recipe,
            **_score(recipe["ingredients"], usable_pantry, staples, today),
            "servings": 1,
            "source": "アプリ内レシピ",
        })
    recipes.sort(key=_rank_key)
    # On "別のレシピを提案", show recipes that were not on screen first.
    excluded = set(exclude_names or [])
    recipes.sort(key=lambda row: row["name"] in excluded)
    return recipes[:3]


def _read_pantry_for_recipes(connection, user_id: str) -> list[PantryInput]:
    """The pantry as stored in SQLite: the single source of truth for suggestions, so a stale
    copy in a browser tab (or another device's edits) can never skew matching or the cache."""
    rows = connection.execute(
        "SELECT name, quantity, unit, expiry_date, category, frozen FROM pantry_items WHERE user_id = ? "
        "ORDER BY expiry_date ASC, created_at DESC LIMIT 200", (user_id,)
    ).fetchall()
    return [PantryInput(name=row["name"], quantity=row["quantity"], unit=row["unit"],
                        expiry_date=date.fromisoformat(row["expiry_date"]), category=row["category"],
                        frozen=bool(row["frozen"])) for row in rows]


@router.post("/suggest")
def suggest_recipes(payload: SuggestRequest, user: CurrentUser) -> dict[str, Any]:
    user_id = user["id"]
    with db_connection() as connection:
        staples = read_staples(connection, user_id)
        pantry = _read_pantry_for_recipes(connection, user_id)
    key = recipe_cache.cache_key(payload, pantry, user_id, staples)

    # 1) Check SQLite cache first, unless the user explicitly asked for different recipes.
    # This path does not call Gemini and does not consume any quota or app-side allowance.
    if not payload.refresh:
        cached = recipe_cache.read_cache(key)
        if cached is not None:
            return cached

    fallback = _format_fallback(pantry, payload.preferences, staples, payload.exclude_recipe_names)

    def local(message: str) -> dict[str, Any]:
        return {"recipes": fallback, "source": "local", "cached": False, "message": message}

    if not GEMINI_API_KEY:
        return local("Gemini APIキーが未設定のため、アプリ内の節約レシピを表示しています。")

    with recipe_limits.rate_lock:
        limit_message = recipe_limits.user_rate_limit_message(user_id) or recipe_limits.reserve_daily_request(user_id)
        if not limit_message:
            recipe_limits.record_user_request(user_id)
    if limit_message:
        return local(f"{limit_message} アプリ内の節約レシピを表示しています。")

    try:
        raw = gemini.generate(gemini.build_prompt(payload, pantry, staples))
        recipes = _format_gemini_recipes(raw, pantry, staples)
        # Enforce user's selected bounds even if the model ignores the prompt.
        recipes = [
            recipe for recipe in recipes
            if recipe["minutes"] <= payload.preferences.max_minutes
            and recipe["estimatedCostYen"] <= payload.preferences.budget_yen
        ]
        if not recipes:
            raise RuntimeError("選択した予算・調理時間に合うレシピを生成できませんでした。食材や予算を変更して再提案してください。")
    except RuntimeError as exc:
        recipe_limits.release_user_daily_request(user_id)
        recipe_limits.forget_user_request(user_id)
        return local(f"{str(exc)} アプリ内の節約レシピを表示しています。")

    result = {
        "recipes": recipes,
        "source": "gemini",
        "cached": False,
        "message": f"{GEMINI_MODEL} が一人分・節約・時短の条件で提案しました。成功した提案はSQLiteに24時間保存し、同じ条件ではAPIを再利用しません。材料費は概算です。",
    }
    recipe_cache.write_cache(key, user_id, result)
    return result
