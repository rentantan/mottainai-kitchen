import re
import time
from datetime import timedelta
from pathlib import Path


import auth
from recipes import FALLBACK_RECIPES, today_japan


def _item(name, days, quantity=1, unit="個", category="その他"):
    return {"name": name, "quantity": quantity, "unit": unit, "category": category,
            "expiryDate": (today_japan() + timedelta(days=days)).isoformat()}


def test_login_locks_after_repeated_failures(client, make_user):
    email, _ = make_user()
    for _ in range(auth.MAX_LOGIN_FAILURES):
        assert client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    locked = client.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert locked.status_code == 429
    auth._clear_login_failures()
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200


def test_successful_login_resets_failure_count(client, make_user):
    email, _ = make_user()
    for _ in range(auth.MAX_LOGIN_FAILURES - 1):
        client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"})
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200
    assert client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200


def test_pantry_is_isolated_per_user(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    client.post("/api/pantry", json=_item("卵", 3), headers=alice)
    assert [i["name"] for i in client.get("/api/pantry", headers=alice).json()["items"]] == ["卵"]
    assert client.get("/api/pantry", headers=bob).json()["items"] == []


def test_consume_reduces_then_removes_item(client, make_user):
    _, headers = make_user()
    item = client.post("/api/pantry", json=_item("卵", 3, quantity=2), headers=headers).json()
    first = client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers).json()
    assert first["item"]["quantity"] == 1
    second = client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers).json()
    assert second["item"] is None and second["consumedCount"] == 1


def test_fallback_recipes_use_expiring_items_with_alias_names(client, make_user):
    _, headers = make_user()
    client.post("/api/pantry", json=_item("鶏もも肉", 0, quantity=250, unit="g", category="肉・魚"), headers=headers)
    client.post("/api/pantry", json=_item("ご飯", 5, quantity=2, unit="杯", category="主食・麺"), headers=headers)
    data = client.post("/api/recipes/suggest", json={"preferences": {"budget_yen": 500, "max_minutes": 20}},
                       headers=headers).json()
    assert data["source"] == "local"
    top = data["recipes"][0]
    assert top["id"] == "teriyaki-chicken-don"
    assert {"鶏肉", "ごはん"} <= set(top["matchedIngredients"])


def test_fallback_recipes_respect_budget_and_time(client, make_user):
    _, headers = make_user()
    data = client.post("/api/recipes/suggest", json={"pantry": [], "preferences": {"budget_yen": 300, "max_minutes": 10}},
                       headers=headers).json()
    assert data["recipes"]
    assert all(r["minutes"] <= 10 and r["estimatedCostYen"] <= 300 for r in data["recipes"])


def test_frontend_fallback_recipes_match_backend():
    """The offline copy in frontend/src/data.ts must list the same recipes as the backend."""
    data_ts = (Path(__file__).resolve().parents[2] / "frontend" / "src" / "data.ts").read_text(encoding="utf-8")
    frontend = re.findall(r"\{ id: '([^']+)', name: '([^']+)'.*?minutes: (\d+).*?estimatedCostYen: (\d+)", data_ts)
    backend = [(r["id"], r["name"], str(r["minutes"]), str(r["estimatedCostYen"])) for r in FALLBACK_RECIPES]
    assert sorted(frontend) == sorted(backend)
    frontend_microwave = set(re.findall(r"\{ id: '([^']+)'[^\n]*microwaveOnly: true", data_ts))
    assert frontend_microwave == {r["id"] for r in FALLBACK_RECIPES if r.get("microwaveOnly")}


def test_discard_is_logged_and_undo_restores_item(client, make_user):
    _, headers = make_user()
    created = client.post("/api/pantry", json=_item("牛乳", -1, unit="本"), headers=headers).json()
    deleted = client.delete(f"/api/pantry/{created['id']}?reason=discarded", headers=headers).json()
    assert deleted["wasteId"] and deleted["item"]["name"] == "牛乳"
    assert deleted["waste"]["totalCount"] == 1 and deleted["waste"]["monthCount"] == 1
    assert client.get("/api/pantry", headers=headers).json()["items"] == []

    item = deleted["item"]
    write = {key: item[key] for key in ("name", "quantity", "unit", "expiryDate", "category", "emoji", "note")}
    restored = client.post("/api/pantry/restore", json={"item": write, "createdAt": item["createdAt"], "wasteId": deleted["wasteId"]},
                           headers=headers).json()
    assert restored["item"]["name"] == "牛乳" and restored["item"]["createdAt"] == item["createdAt"]
    assert restored["waste"]["totalCount"] == 0
    assert [i["name"] for i in client.get("/api/pantry", headers=headers).json()["items"]] == ["牛乳"]


def test_plain_delete_is_not_logged_as_waste(client, make_user):
    _, headers = make_user()
    created = client.post("/api/pantry", json=_item("卵", 3), headers=headers).json()
    deleted = client.delete(f"/api/pantry/{created['id']}", headers=headers).json()
    assert deleted["wasteId"] is None and deleted["waste"]["totalCount"] == 0


def test_waste_log_is_private_and_cleared_by_reset(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    created = client.post("/api/pantry", json=_item("豆腐", -2, unit="丁"), headers=alice).json()
    deleted = client.delete(f"/api/pantry/{created['id']}?reason=discarded", headers=alice).json()
    # Bob cannot remove Alice's waste entry through restore.
    client.post("/api/pantry/restore", json={"item": _item("卵", 3), "wasteId": deleted["wasteId"]}, headers=bob)
    assert client.get("/api/pantry", headers=alice).json()["waste"]["totalCount"] == 1
    assert client.get("/api/pantry", headers=bob).json()["waste"]["totalCount"] == 0
    reset = client.put("/api/pantry/reset?reset_records=true", json=[], headers=alice).json()
    assert reset["waste"]["totalCount"] == 0


def test_invalid_delete_reason_is_rejected(client, make_user):
    _, headers = make_user()
    created = client.post("/api/pantry", json=_item("卵", 3), headers=headers).json()
    assert client.delete(f"/api/pantry/{created['id']}?reason=whatever", headers=headers).status_code == 422


def test_frozen_flag_and_price_round_trip(client, make_user):
    _, headers = make_user()
    created = client.post("/api/pantry", json={**_item("鶏もも肉", 2, quantity=300, unit="g"), "priceYen": 450},
                          headers=headers).json()
    assert created["frozen"] is False and created["priceYen"] == 450 and created["purchasedQuantity"] == 300
    write = {key: created[key] for key in ("name", "quantity", "unit", "expiryDate", "category", "emoji", "note", "priceYen")}
    frozen = client.put(f"/api/pantry/{created['id']}", json={**write, "frozen": True}, headers=headers).json()
    assert frozen["frozen"] is True and frozen["purchasedQuantity"] == 300


def test_discarded_value_is_proportional_to_what_was_left(client, make_user):
    _, headers = make_user()
    created = client.post("/api/pantry", json={**_item("鶏もも肉", -1, quantity=300, unit="g"), "priceYen": 450},
                          headers=headers).json()
    client.post(f"/api/pantry/{created['id']}/consume", json={"amount": 200}, headers=headers)
    waste = client.delete(f"/api/pantry/{created['id']}?reason=discarded", headers=headers).json()["waste"]
    assert waste["items"][0]["valueYen"] == 150
    assert waste["monthYen"] == 150 and waste["totalYen"] == 150
    # Items without a price are counted but add no yen.
    other = client.post("/api/pantry", json=_item("豆腐", -1, unit="丁"), headers=headers).json()
    waste = client.delete(f"/api/pantry/{other['id']}?reason=discarded", headers=headers).json()["waste"]
    assert waste["monthCount"] == 2 and waste["monthYen"] == 150


def test_microwave_mode_only_returns_stove_free_recipes(client, make_user):
    _, headers = make_user()
    data = client.post("/api/recipes/suggest", json={"pantry": [], "preferences": {"budget_yen": 700, "max_minutes": 30, "equipment": "microwave"}},
                       headers=headers).json()
    microwave_ids = {r["id"] for r in FALLBACK_RECIPES if r.get("microwaveOnly")}
    assert data["recipes"] and {r["id"] for r in data["recipes"]} <= microwave_ids


def test_frozen_items_are_flagged_in_prompt():
    from models import PantryInput, SuggestRequest
    from recipes import _build_prompt
    pantry = [PantryInput(name="ごはん", quantity=2, unit="杯", category="主食・麺",
                          expiry_date=today_japan() + timedelta(days=30), frozen=True)]
    prompt = _build_prompt(SuggestRequest(preferences={"equipment": "microwave"}), pantry, [])
    assert "冷凍保存中" in prompt and "電子レンジ（と電気ケトル・炊飯器）だけ" in prompt


def _write(item):
    return {key: item[key] for key in ("name", "quantity", "unit", "expiryDate", "category", "emoji", "note")}


def test_undo_partial_and_full_consume(client, make_user):
    _, headers = make_user()
    item = client.post("/api/pantry", json=_item("卵", 3, quantity=4), headers=headers).json()
    partial = client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers).json()
    state = client.post("/api/pantry/undo-consume", json={"entries": [{"logId": partial["logId"]}]}, headers=headers).json()
    assert state["items"][0]["quantity"] == 4

    full = client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 4}, headers=headers).json()
    assert full["item"] is None and full["consumedCount"] == 1 and full["waste"]["monthUsedUp"] == 1
    state = client.post("/api/pantry/undo-consume", json={"entries": [{"logId": full["logId"], "item": _write(item),
                                                                      "createdAt": item["createdAt"]}]}, headers=headers).json()
    assert [(i["name"], i["quantity"]) for i in state["items"]] == [("卵", 4)]
    assert state["consumedCount"] == 0 and state["waste"]["monthUsedUp"] == 0
    # A log entry can only be undone once.
    again = client.post("/api/pantry/undo-consume", json={"entries": [{"logId": full["logId"], "item": _write(item)}]}, headers=headers)
    assert again.status_code == 404


def test_undo_consume_batch_and_other_users_logs(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    egg = client.post("/api/pantry", json=_item("卵", 3, quantity=2), headers=alice).json()
    milk = client.post("/api/pantry", json=_item("牛乳", 3, quantity=1, unit="本"), headers=alice).json()
    state = client.post("/api/pantry/consume-batch", json={"items": [{"id": egg["id"], "amount": 1}, {"id": milk["id"], "amount": 1}]},
                        headers=alice).json()
    assert len(state["logIds"]) == 2
    entries = [{"logId": state["logIds"][0]}, {"logId": state["logIds"][1], "item": _write(milk), "createdAt": milk["createdAt"]}]
    assert client.post("/api/pantry/undo-consume", json={"entries": entries}, headers=bob).status_code == 404
    restored = client.post("/api/pantry/undo-consume", json={"entries": entries}, headers=alice).json()
    assert sorted((i["name"], i["quantity"]) for i in restored["items"]) == [("卵", 2), ("牛乳", 1)]


def test_reset_can_keep_records(client, make_user):
    _, headers = make_user()
    created = client.post("/api/pantry", json=_item("豆腐", -1, unit="丁"), headers=headers).json()
    client.delete(f"/api/pantry/{created['id']}?reason=discarded", headers=headers)
    kept = client.put("/api/pantry/reset", json=[], headers=headers).json()
    assert kept["items"] == [] and kept["waste"]["totalCount"] == 1
    cleared = client.put("/api/pantry/reset?reset_records=true", json=[], headers=headers).json()
    assert cleared["waste"]["totalCount"] == 0


def test_lockout_is_per_ip_so_strangers_cannot_lock_you_out(client, make_user, monkeypatch):
    email, _ = make_user()
    monkeypatch.setattr(auth, "_client_ip", lambda request: "203.0.113.9")  # the attacker's network
    for _ in range(auth.MAX_LOGIN_FAILURES):
        client.post("/api/auth/login", json={"email": email, "password": "wrong-pass"})
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 429
    # The owner, from their own network, can still log in.
    monkeypatch.setattr(auth, "_client_ip", lambda request: "198.51.100.7")
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 200


def test_registration_is_rate_limited_per_ip(client, monkeypatch):
    monkeypatch.setattr(auth, "MAX_REGISTRATIONS_PER_IP", 2)
    for n in range(2):
        assert client.post("/api/auth/register", json={"email": f"r{n}-{time.time()}@example.com", "password": "password123"}).status_code == 200
    assert client.post("/api/auth/register", json={"email": f"r9-{time.time()}@example.com", "password": "password123"}).status_code == 429


def test_change_password_logs_out_other_devices(client, make_user):
    email, headers = make_user()
    other = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]}
    assert client.post("/api/auth/password", json={"currentPassword": "wrong", "newPassword": "newpassword1"}, headers=headers).status_code == 403
    assert client.post("/api/auth/password", json={"currentPassword": "password123", "newPassword": "newpassword1"}, headers=headers).status_code == 200
    assert client.get("/api/pantry", headers=headers).status_code == 200
    assert client.get("/api/pantry", headers=other).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "newpassword1"}).status_code == 200


def test_logout_other_devices_keeps_current_session(client, make_user):
    email, headers = make_user()
    other = {"Authorization": "Bearer " + client.post("/api/auth/login", json={"email": email, "password": "password123"}).json()["token"]}
    assert client.post("/api/auth/logout-others", headers=headers).json()["loggedOut"] == 1
    assert client.get("/api/pantry", headers=headers).status_code == 200
    assert client.get("/api/pantry", headers=other).status_code == 401


def test_delete_account_removes_all_data(client, make_user):
    email, headers = make_user()
    client.post("/api/pantry", json=_item("卵", 3), headers=headers)
    client.post("/api/shopping", json={"names": ["もやし"]}, headers=headers)
    assert client.request("DELETE", "/api/auth/account", json={"password": "wrong"}, headers=headers).status_code == 403
    assert client.request("DELETE", "/api/auth/account", json={"password": "password123"}, headers=headers).status_code == 200
    assert client.get("/api/pantry", headers=headers).status_code == 401
    assert client.post("/api/auth/login", json={"email": email, "password": "password123"}).status_code == 401
    # The address can be registered again from scratch.
    fresh = client.post("/api/auth/register", json={"email": email, "password": "password123"}).json()
    assert client.get("/api/pantry", headers={"Authorization": f"Bearer {fresh['token']}"}).json()["items"] == []


def test_shopping_list_skips_other_spellings(client, make_user):
    _, headers = make_user()
    client.post("/api/shopping", json={"names": ["長ねぎ", "醤油"]}, headers=headers)
    result = client.post("/api/shopping", json={"names": ["ネギ", "しょうゆ", "玉ねぎ", "玉葱"]}, headers=headers).json()
    assert result["added"] == 1 and sorted(i["name"] for i in result["items"]) == sorted(["長ねぎ", "醤油", "玉ねぎ"])


def test_relative_database_path_is_resolved_from_backend_dir(monkeypatch):
    import config
    monkeypatch.setenv("DATABASE_PATH", "data/x.db")
    assert config._database_path() == str(Path(config.__file__).resolve().parent / "data" / "x.db")
    monkeypatch.setenv("DATABASE_PATH", "/tmp/abs.db")
    assert config._database_path() == "/tmp/abs.db"


def test_undo_consume_does_not_resurrect_deleted_item(client, make_user):
    """Partly used, then deleted: undoing the old "使った" must not bring the item back."""
    _, headers = make_user()
    item = client.post("/api/pantry", json=_item("卵", 3, quantity=4), headers=headers).json()
    log_id = client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers).json()["logId"]
    client.delete(f"/api/pantry/{item['id']}?reason=discarded", headers=headers)
    before = {k: v for k, v in item.items() if k not in ("id", "createdAt")}
    response = client.post("/api/pantry/undo-consume", json={"entries": [{"logId": log_id, "item": before}]}, headers=headers)
    assert response.status_code == 409
    assert client.get("/api/pantry", headers=headers).json()["items"] == []



def test_concurrent_consumes_do_not_lose_updates(client, make_user):
    """Two devices pressing "使った" at the same time must both be counted."""
    from concurrent.futures import ThreadPoolExecutor
    _, headers = make_user()
    item = client.post("/api/pantry", json=_item("卵", 3, quantity=10), headers=headers).json()

    def use_one(_):
        return client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert set(pool.map(use_one, range(8))) == {200}
    assert client.get("/api/pantry", headers=headers).json()["items"][0]["quantity"] == 2


def test_login_required_messages_and_docs(client):
    missing = client.get("/api/pantry")
    assert missing.status_code == 401 and missing.json()["detail"] == "ログインが必要です"
    wrong = client.get("/api/pantry", headers={"Authorization": "Bearer not-a-token"})
    assert wrong.status_code == 401 and wrong.json()["detail"] == "ログインの有効期限が切れています"
    # Every endpoint that needs a login is marked as such in the OpenAPI docs.
    paths = client.get("/openapi.json").json()["paths"]
    assert "security" in paths["/api/pantry"]["get"] and "security" in paths["/api/recipes/suggest"]["post"]
    assert "security" not in paths["/api/auth/login"]["post"]


def test_stock_from_shopping_registers_and_ticks_off(client, make_user):
    _, headers = make_user()
    rows = client.post("/api/shopping", json={"names": ["卵", "もやし"]}, headers=headers).json()["items"]
    egg = next(r for r in rows if r["name"] == "卵")
    sprouts = next(r for r in rows if r["name"] == "もやし")
    client.delete(f"/api/shopping/{sprouts['id']}", headers=headers)
    body = {"entries": [{"shoppingId": egg["id"], "item": _item("卵", 14, quantity=6)},
                        {"shoppingId": sprouts["id"], "item": _item("もやし", 2)}]}
    result = client.post("/api/shopping/stock", json=body, headers=headers).json()
    # The deleted row is skipped; the egg is added and ticked off.
    assert [i["name"] for i in result["added"]] == ["卵"]
    assert result["items"] == [{**egg, "checked": True}]
    assert len(client.get("/api/pantry", headers=headers).json()["items"]) == 1
