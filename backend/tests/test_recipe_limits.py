"""Gemini path: cache vs. "別のレシピを提案", and per-account call limits. Gemini itself is stubbed."""
from datetime import timedelta

import pytest

import gemini as gemini_client
import recipe_limits
import recipes
from clock import today_japan
from database import db_connection

PANTRY = [{"name": "卵", "quantity": 6, "unit": "個", "category": "乳製品・卵",
           "expiryDate": (today_japan() + timedelta(days=2)).isoformat()}]


def _gemini_recipe(name):
    return {"name": name, "description": "説明", "minutes": 10, "difficulty": "かんたん", "emoji": "🍳",
            "ingredients": ["卵"], "ingredientDetails": ["卵 1個"], "steps": ["焼く"], "estimatedCostYen": 100}


@pytest.fixture
def gemini(monkeypatch):
    """Pretend an API key is set and record every prompt sent to the stubbed Gemini."""
    calls = {"prompts": [], "fail": False}

    def fake_generate(prompt):
        calls["prompts"].append(prompt)
        if calls["fail"]:
            raise RuntimeError("Gemini APIが一時的に混雑しています。")
        n = len(calls["prompts"])
        return {"recipes": [_gemini_recipe(f"案{n}-{i}") for i in range(3)]}

    monkeypatch.setattr(recipes, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(gemini_client, "generate", fake_generate)
    monkeypatch.setattr(recipe_limits, "MIN_REQUEST_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(recipe_limits, "MAX_REQUESTS_PER_HOUR_PER_USER", 100)
    monkeypatch.setattr(recipe_limits, "MAX_REQUESTS_PER_DAY", 100)
    monkeypatch.setattr(recipe_limits, "MAX_REQUESTS_PER_DAY_PER_USER", 2)
    recipe_limits._request_history.clear()
    recipe_limits._last_request_at.clear()
    with db_connection() as connection:
        connection.execute("DELETE FROM gemini_daily_usage")
        connection.execute("DELETE FROM gemini_user_daily_usage")
        connection.execute("DELETE FROM recipe_suggestion_cache")
    return calls


def _suggest(client, headers, **extra):
    """Suggest from the user's stored pantry (seeded with PANTRY on first use)."""
    if not client.get("/api/pantry", headers=headers).json()["items"]:
        for item in PANTRY:
            client.post("/api/pantry", json=item, headers=headers)
    body = {"preferences": {"budget_yen": 500, "max_minutes": 20}, **extra}
    return client.post("/api/recipes/suggest", json=body, headers=headers).json()


def test_suggest_uses_stored_pantry_not_client_copy(client, make_user, gemini):
    """The server's pantry is the source of truth: a pantry list sent by the client is ignored."""
    _, headers = make_user()
    _suggest(client, headers)
    assert "卵" in gemini["prompts"][0]
    body = {"pantry": [{"name": "キャビア", "quantity": 1, "unit": "個", "category": "その他",
                        "expiry_date": today_japan().isoformat()}],
            "preferences": {"budget_yen": 500, "max_minutes": 20}, "refresh": True}
    client.post("/api/recipes/suggest", json=body, headers=headers)
    assert "キャビア" not in gemini["prompts"][1] and "卵" in gemini["prompts"][1]


def test_pantry_change_invalidates_cache(client, make_user, gemini):
    _, headers = make_user()
    _suggest(client, headers)
    item = client.get("/api/pantry", headers=headers).json()["items"][0]
    client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers)
    assert _suggest(client, headers)["cached"] is False
    assert len(gemini["prompts"]) == 2


def test_same_conditions_reuse_cache(client, make_user, gemini):
    _, headers = make_user()
    first = _suggest(client, headers)
    second = _suggest(client, headers)
    assert first["source"] == "gemini" and second["cached"] is True
    assert len(gemini["prompts"]) == 1


def test_refresh_skips_cache_and_avoids_shown_recipes(client, make_user, gemini):
    _, headers = make_user()
    shown = [r["name"] for r in _suggest(client, headers)["recipes"]]
    refreshed = _suggest(client, headers, refresh=True, exclude_recipe_names=shown)
    assert refreshed["source"] == "gemini" and not refreshed["cached"]
    assert {r["name"] for r in refreshed["recipes"]}.isdisjoint(shown)
    assert all(name in gemini["prompts"][1] for name in shown)
    # The refreshed result replaces the cache entry for these conditions.
    again = _suggest(client, headers)
    assert again["cached"] and [r["name"] for r in again["recipes"]] == [r["name"] for r in refreshed["recipes"]]


def test_daily_limit_is_per_user(client, make_user, gemini):
    _, alice = make_user()
    _, bob = make_user()
    assert _suggest(client, alice)["source"] == "gemini"
    assert _suggest(client, alice, refresh=True)["source"] == "gemini"
    limited = _suggest(client, alice, refresh=True)
    assert limited["source"] == "local" and "1人1日2回" in limited["message"]
    # Alice using up her allowance does not block Bob.
    assert _suggest(client, bob)["source"] == "gemini"


def test_app_wide_daily_cap_still_applies(client, make_user, gemini, monkeypatch):
    monkeypatch.setattr(recipe_limits, "MAX_REQUESTS_PER_DAY", 1)
    _, alice = make_user()
    _, bob = make_user()
    assert _suggest(client, alice)["source"] == "gemini"
    limited = _suggest(client, bob)
    assert limited["source"] == "local" and "アプリ全体" in limited["message"]


def test_failed_call_is_not_charged_to_user(client, make_user, gemini):
    _, headers = make_user()
    gemini["fail"] = True
    for _ in range(3):
        assert _suggest(client, headers, refresh=True)["source"] == "local"
    gemini["fail"] = False
    assert _suggest(client, headers, refresh=True)["source"] == "gemini"


def test_interval_limit_is_per_user(client, make_user, gemini, monkeypatch):
    monkeypatch.setattr(recipe_limits, "MIN_REQUEST_INTERVAL_SECONDS", 60)
    _, alice = make_user()
    _, bob = make_user()
    assert _suggest(client, alice)["source"] == "gemini"
    assert "60秒" in _suggest(client, alice, refresh=True)["message"]
    assert _suggest(client, bob)["source"] == "gemini"


def test_local_refresh_rotates_fallback_recipes(client, make_user):
    _, headers = make_user()
    body = {"pantry": [], "preferences": {"budget_yen": 700, "max_minutes": 30}}
    shown = [r["name"] for r in client.post("/api/recipes/suggest", json=body, headers=headers).json()["recipes"]]
    other = client.post("/api/recipes/suggest", json={**body, "refresh": True, "exclude_recipe_names": shown},
                        headers=headers).json()["recipes"]
    assert {r["name"] for r in other}.isdisjoint(shown)
