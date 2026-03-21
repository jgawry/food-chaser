"""Tests for GET /api/deals/my-list — deals filtered by grocery list."""
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
    """Insert a variety of deals for matching tests."""
    deals = [
        {"product_id": "p1", "name": "Mleko UHT 3.2%", "category": "Nabiał", "price": 3.99, "discount_pct": 20},
        {"product_id": "p2", "name": "Chleb pszenny", "category": "Pieczywo", "price": 2.49, "discount_pct": 15},
        {"product_id": "p3", "name": "Masło extra 200g", "category": "Nabiał", "price": 5.99, "discount_pct": 10},
        {"product_id": "p4", "name": "Sok pomarańczowy 1L", "category": "Napoje", "price": 4.49, "discount_pct": 25},
        {"product_id": "p5", "name": "Mleko kozie", "category": "Nabiał", "price": 6.99, "discount_pct": 5},
    ]
    save_deals(flask_app, deals)
    return deals


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestDealsMyList:
    def test_requires_auth(self, client):
        resp = client.get("/api/deals/my-list")
        assert resp.status_code == 401

    def test_empty_grocery_list_returns_no_deals(self, client, auth_token, deals_in_db):
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["deals"] == []
        assert data["count"] == 0

    def test_matches_single_item(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Chleb"})
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        assert resp.status_code == 200
        deals = resp.get_json()["deals"]
        assert len(deals) == 1
        assert deals[0]["name"] == "Chleb pszenny"
        assert "Chleb" in deals[0]["matched_items"]

    def test_matches_multiple_items(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Masło"})
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        deals = resp.get_json()["deals"]
        assert len(deals) == 3  # Mleko UHT, Mleko kozie, Masło extra
        names = {d["name"] for d in deals}
        assert "Mleko UHT 3.2%" in names
        assert "Mleko kozie" in names
        assert "Masło extra 200g" in names

    def test_case_insensitive_matching(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "mleko"})
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        deals = resp.get_json()["deals"]
        assert len(deals) == 2  # Mleko UHT, Mleko kozie

    def test_category_filter(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        resp = client.get("/api/deals/my-list?category=Nabiał", headers=_auth_headers(auth_token))
        deals = resp.get_json()["deals"]
        assert len(deals) == 2
        assert all(d["category"] == "Nabiał" for d in deals)

    def test_no_matching_deals(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Ryż"})
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        assert resp.get_json()["deals"] == []

    def test_matched_items_annotation(self, client, flask_app, auth_token, deals_in_db):
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Mleko"})
        client.post("/api/grocery-list", headers=_auth_headers(auth_token), json={"name": "Sok"})
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        deals = resp.get_json()["deals"]
        for deal in deals:
            assert "matched_items" in deal
            assert len(deal["matched_items"]) >= 1

    def test_only_own_grocery_list_used(self, client, flask_app, auth_token):
        """Another user's grocery list should not affect results."""
        deals_data = [
            {"product_id": "p1", "name": "Mleko UHT", "category": "Nabiał", "price": 3.99, "discount_pct": 20},
        ]
        save_deals(flask_app, deals_data)

        # Second user adds "Mleko" to their list
        with patch("app.email_report.send_confirmation_email"):
            client.post("/api/auth/register", json={"email": "other@example.com", "password": "password123"})
        _confirm(client, flask_app, email="other@example.com")
        other_token = _login(client, email="other@example.com")
        client.post("/api/grocery-list", headers=_auth_headers(other_token), json={"name": "Mleko"})

        # First user (empty list) should see no matches
        resp = client.get("/api/deals/my-list", headers=_auth_headers(auth_token))
        assert resp.get_json()["deals"] == []
