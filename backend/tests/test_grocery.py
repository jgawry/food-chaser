"""Integration tests for grocery list routes: CRUD + ownership isolation."""
from unittest.mock import patch

import pytest

from app.db import _connect


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register(client, email="user@example.com", password="password123"):
    with patch("app.email_report.send_confirmation_email"):
        return client.post("/api/auth/register", json={"email": email, "password": password})


def _confirm(client, flask_app, email="user@example.com"):
    with _connect(flask_app) as conn:
        row = conn.execute(
            "SELECT t.token FROM email_confirmation_tokens t "
            "JOIN users u ON t.user_id = u.id WHERE u.email = ?",
            (email,),
        ).fetchone()
    assert row, f"No confirmation token for {email}"
    client.get(f"/api/auth/confirm/{row[0]}")


def _login(client, email="user@example.com", password="password123"):
    resp = client.post("/api/auth/login", json={"email": email, "password": password})
    return resp.get_json()["token"]


def _auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_token(client, flask_app):
    _register(client)
    _confirm(client, flask_app)
    return _login(client)


@pytest.fixture
def second_token(client, flask_app):
    _register(client, email="other@example.com")
    _confirm(client, flask_app, email="other@example.com")
    return _login(client, email="other@example.com")


# ── GET /api/grocery-list ─────────────────────────────────────────────────────

class TestListItems:
    def test_empty_list(self, client, auth_token):
        resp = client.get("/api/grocery-list", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        assert resp.get_json()["items"] == []

    def test_returns_user_items(self, client, auth_token):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Milk"})
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Bread"})
        resp = client.get("/api/grocery-list", headers=_auth_headers(auth_token))
        items = resp.get_json()["items"]
        assert len(items) == 2
        names = {i["name"] for i in items}
        assert names == {"Milk", "Bread"}

    def test_requires_auth(self, client):
        resp = client.get("/api/grocery-list")
        assert resp.status_code == 401


# ── POST /api/grocery-list ────────────────────────────────────────────────────

class TestAddItem:
    def test_add_item(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Eggs", "quantity": "10"})
        assert resp.status_code == 201
        item = resp.get_json()["item"]
        assert item["name"] == "Eggs"
        assert item["quantity"] == "10"
        assert "id" in item

    def test_add_item_without_quantity(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Butter"})
        assert resp.status_code == 201
        assert resp.get_json()["item"]["quantity"] is None

    def test_empty_name_returns_400(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": ""})
        assert resp.status_code == 400

    def test_missing_name_returns_400(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={})
        assert resp.status_code == 400

    def test_whitespace_name_returns_400(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "   "})
        assert resp.status_code == 400

    def test_requires_auth(self, client):
        resp = client.post("/api/grocery-list", json={"name": "Milk"})
        assert resp.status_code == 401


# ── PUT /api/grocery-list/<id> ────────────────────────────────────────────────

class TestUpdateItem:
    def test_update_name_and_quantity(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Milk"})
        item_id = resp.get_json()["item"]["id"]
        resp = client.put(f"/api/grocery-list/{item_id}", headers=_auth_headers(auth_token), json={"name": "Whole Milk", "quantity": "2L"})
        assert resp.status_code == 200
        item = resp.get_json()["item"]
        assert item["name"] == "Whole Milk"
        assert item["quantity"] == "2L"

    def test_empty_name_returns_400(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Milk"})
        item_id = resp.get_json()["item"]["id"]
        resp = client.put(f"/api/grocery-list/{item_id}", headers=_auth_headers(auth_token), json={"name": ""})
        assert resp.status_code == 400

    def test_nonexistent_item_returns_404(self, client, auth_token):
        resp = client.put("/api/grocery-list/9999", headers=_auth_headers(auth_token), json={"name": "Milk"})
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.put("/api/grocery-list/1", json={"name": "Milk"})
        assert resp.status_code == 401


# ── DELETE /api/grocery-list/<id> ─────────────────────────────────────────────

class TestDeleteItem:
    def test_delete_item(self, client, auth_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Milk"})
        item_id = resp.get_json()["item"]["id"]
        resp = client.delete(f"/api/grocery-list/{item_id}", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        assert resp.get_json()["deleted"] is True
        # Verify gone
        resp = client.get("/api/grocery-list", headers=_auth_headers(auth_token))
        assert resp.get_json()["items"] == []

    def test_nonexistent_item_returns_404(self, client, auth_token):
        resp = client.delete("/api/grocery-list/9999", headers=_auth_headers(auth_token))
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        resp = client.delete("/api/grocery-list/1")
        assert resp.status_code == 401


# ── Ownership isolation ───────────────────────────────────────────────────────

class TestOwnership:
    def test_user_cannot_see_other_users_items(self, client, auth_token, second_token):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "User1 item"})
        client.post("/api/grocery-list", headers=_auth_headers(second_token), json={"name": "User2 item"})
        resp = client.get("/api/grocery-list", headers=_auth_headers(auth_token))
        items = resp.get_json()["items"]
        assert len(items) == 1
        assert items[0]["name"] == "User1 item"

    def test_user_cannot_update_other_users_items(self, client, auth_token, second_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "User1 item"})
        item_id = resp.get_json()["item"]["id"]
        resp = client.put(f"/api/grocery-list/{item_id}", headers=_auth_headers(second_token), json={"name": "Hacked"})
        assert resp.status_code == 404

    def test_user_cannot_delete_other_users_items(self, client, auth_token, second_token):
        resp = client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "User1 item"})
        item_id = resp.get_json()["item"]["id"]
        resp = client.delete(f"/api/grocery-list/{item_id}", headers=_auth_headers(second_token))
        assert resp.status_code == 404
        # Verify still exists for owner
        resp = client.get("/api/grocery-list", headers=_auth_headers(auth_token))
        assert len(resp.get_json()["items"]) == 1
