"""Tests for GET /api/deals/optimize — best deals per grocery list item."""
from unittest.mock import patch

import pytest

from app.db import _connect, save_deals


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
def deals_in_db(flask_app):
    deals = [
        {"product_id": "p1", "name": "Mleko UHT 3.2% 1L", "category": "Nabiał", "price": 2.99, "old_price": 3.49},
        {"product_id": "p2", "name": "Mleko kozie 500ml", "category": "Nabiał", "price": 4.99},
        {"product_id": "p3", "name": "Mleko UHT 2% 1L", "category": "Nabiał", "price": 2.49, "old_price": 2.99},
        {"product_id": "p4", "name": "Chleb pszenny", "category": "Pieczywo", "price": 3.29},
        {"product_id": "p5", "name": "Masło extra 200g", "category": "Nabiał", "price": 5.99, "old_price": 7.49},
    ]
    save_deals(flask_app, deals)
    return deals


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDealsOptimize:
    def test_requires_auth(self, client):
        resp = client.get("/api/deals/optimize")
        assert resp.status_code == 401

    def test_empty_grocery_list(self, client, auth_token, deals_in_db):
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["items"] == []
        assert data["total_savings"] == 0.0

    def test_unmatched_item_has_null_best_deal(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Ryż"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        data = resp.get_json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["grocery_item"]["name"] == "Ryż"
        assert item["best_deal"] is None
        assert item["alternatives"] == []

    def test_matched_item_returns_cheapest_as_best_deal(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        data = resp.get_json()
        assert len(data["items"]) == 1
        item = data["items"][0]
        # Three mleko deals: prices 2.99, 4.99, 2.49 → cheapest is 2.49
        assert item["best_deal"]["price"] == 2.49
        assert item["best_deal"]["name"] == "Mleko UHT 2% 1L"

    def test_alternatives_are_remaining_deals_in_price_order(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        item = resp.get_json()["items"][0]
        assert len(item["alternatives"]) == 2
        # Remaining deals ordered by price: 2.99, 4.99
        assert item["alternatives"][0]["price"] == 2.99
        assert item["alternatives"][1]["price"] == 4.99

    def test_total_savings_sums_best_deal_old_price_minus_price(self, client, flask_app, auth_token, deals_in_db):
        # Mleko: best = 2.49 (old 2.99), savings = 0.50
        # Masło: best = 5.99 (old 7.49), savings = 1.50
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Masło"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        data = resp.get_json()
        assert data["total_savings"] == pytest.approx(2.0)

    def test_total_savings_excludes_items_without_old_price(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Chleb"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        data = resp.get_json()
        assert data["total_savings"] == 0.0

    def test_grocery_item_fields_included(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token),
                    json={"name": "Mleko", "quantity": "2L"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        gi = resp.get_json()["items"][0]["grocery_item"]
        assert gi["name"] == "Mleko"
        assert gi["quantity"] == "2L"
        assert "id" in gi

    def test_mixed_matched_and_unmatched(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Ryż"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        data = resp.get_json()
        assert len(data["items"]) == 2
        matched = [i for i in data["items"] if i["best_deal"] is not None]
        unmatched = [i for i in data["items"] if i["best_deal"] is None]
        assert len(matched) == 1
        assert len(unmatched) == 1
        assert unmatched[0]["grocery_item"]["name"] == "Ryż"

    def test_only_own_grocery_list_used(self, client, flask_app, auth_token, deals_in_db):
        with patch("app.email_report.send_confirmation_email"):
            client.post("/api/auth/register", json={"email": "other@example.com", "password": "password123"})
        _confirm(client, flask_app, email="other@example.com")
        other_token = _login(client, email="other@example.com")
        client.post("/api/grocery-list", headers=_auth_headers(other_token), json={"name": "Mleko"})

        # First user has no items — should see empty result
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        assert resp.get_json()["items"] == []

    def test_single_matching_deal_has_no_alternatives(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Chleb"})
        resp = client.get("/api/deals/optimize", headers=_auth_headers(auth_token))
        item = resp.get_json()["items"][0]
        assert item["best_deal"] is not None
        assert item["alternatives"] == []
