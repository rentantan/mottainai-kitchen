"""Saved (favourite) recipes: per-user, de-duplicated by name, capped, removed with the account."""
import saved_recipes


def _recipe(name="卵チャーハン", **extra):
    return {
        "name": name, "description": "簡単", "minutes": 10, "difficulty": "かんたん", "emoji": "🍳",
        "ingredients": ["ごはん", "卵"], "ingredientDetails": ["ごはん 1杯", "卵 1個", "余分な行"],
        "steps": ["炒める"], "estimatedCostYen": 120, "source": "Gemini", **extra,
    }


def test_save_list_and_delete(client, make_user):
    _, headers = make_user()
    saved = client.post("/api/recipes/saved", json=_recipe(), headers=headers)
    assert saved.status_code == 200
    items = saved.json()["items"]
    assert [item["recipe"]["name"] for item in items] == ["卵チャーハン"]
    # Details are trimmed to match the ingredient rows; pantry-dependent fields are not stored.
    assert items[0]["recipe"]["ingredientDetails"] == ["ごはん 1杯", "卵 1個"]
    assert "matchedIngredients" not in items[0]["recipe"]
    assert client.get("/api/recipes/saved", headers=headers).json()["items"] == items
    remaining = client.delete(f"/api/recipes/saved/{saved.json()['id']}", headers=headers).json()["items"]
    assert remaining == []


def test_saving_same_name_replaces_instead_of_duplicating(client, make_user):
    _, headers = make_user()
    first = client.post("/api/recipes/saved", json=_recipe(), headers=headers).json()
    second = client.post("/api/recipes/saved", json=_recipe(" 卵チャーハン ", minutes=8), headers=headers).json()
    assert second["id"] == first["id"]
    assert len(second["items"]) == 1
    assert second["items"][0]["recipe"]["minutes"] == 8


def test_saved_recipes_are_per_user(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    saved_id = client.post("/api/recipes/saved", json=_recipe(), headers=alice).json()["id"]
    assert client.get("/api/recipes/saved", headers=bob).json()["items"] == []
    client.delete(f"/api/recipes/saved/{saved_id}", headers=bob)  # someone else's id: no effect
    assert len(client.get("/api/recipes/saved", headers=alice).json()["items"]) == 1


def test_saved_recipes_need_login_and_ingredients(client, make_user):
    assert client.get("/api/recipes/saved").status_code == 401
    _, headers = make_user()
    assert client.post("/api/recipes/saved", json=_recipe(ingredients=[]), headers=headers).status_code == 422


def test_saved_recipes_are_capped(client, make_user, monkeypatch):
    monkeypatch.setattr(saved_recipes, "MAX_SAVED_RECIPES", 2)
    _, headers = make_user()
    for name in ("A", "B"):
        assert client.post("/api/recipes/saved", json=_recipe(name), headers=headers).status_code == 200
    assert client.post("/api/recipes/saved", json=_recipe("C"), headers=headers).status_code == 400
    # Re-saving an existing one still works at the cap.
    assert client.post("/api/recipes/saved", json=_recipe("A"), headers=headers).status_code == 200


def test_deleting_account_removes_saved_recipes(client, make_user):
    _, headers = make_user()
    saved_id = client.post("/api/recipes/saved", json=_recipe(), headers=headers).json()["id"]
    assert client.request("DELETE", "/api/auth/account", json={"password": "password123"}, headers=headers).status_code == 200
    import database
    with database.db_connection() as connection:
        assert connection.execute("SELECT COUNT(*) FROM saved_recipes WHERE id = ?", (saved_id,)).fetchone()[0] == 0
