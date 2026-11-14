"""Restock suggestions: foods the user used up recently, for one-tap re-adding to the shopping list."""
from datetime import timedelta

from recipes import today_japan


def _item(name, quantity=1):
    return {"name": name, "quantity": quantity, "unit": "個", "category": "その他",
            "expiryDate": (today_japan() + timedelta(days=3)).isoformat()}


def _use_up(client, headers, name):
    item = client.post("/api/pantry", json=_item(name), headers=headers).json()
    return client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers).json()


def test_lists_used_up_foods_newest_first_without_duplicates(client, make_user):
    _, headers = make_user()
    _use_up(client, headers, "卵")
    _use_up(client, headers, "牛乳")
    _use_up(client, headers, "たまご")  # same food as 卵: listed once, under the newest spelling
    names = client.get("/api/shopping/restock", headers=headers).json()["names"]
    assert names == ["たまご", "牛乳"]


def test_partly_used_and_undone_foods_are_not_listed(client, make_user):
    _, headers = make_user()
    item = client.post("/api/pantry", json=_item("豆腐", quantity=2), headers=headers).json()
    client.post(f"/api/pantry/{item['id']}/consume", json={"amount": 1}, headers=headers)
    result = _use_up(client, headers, "納豆")
    before = {"name": "納豆", **_item("納豆")}
    client.post("/api/pantry/undo-consume", json={"entries": [{"logId": result["logId"], "item": before}]}, headers=headers)
    assert client.get("/api/shopping/restock", headers=headers).json()["names"] == []


def test_restock_is_per_user(client, make_user):
    _, alice = make_user()
    _, bob = make_user()
    _use_up(client, alice, "卵")
    assert client.get("/api/shopping/restock", headers=bob).json()["names"] == []
