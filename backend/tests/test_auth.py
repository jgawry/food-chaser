"""Integration tests for authentication routes: register, confirm, login, me."""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import jwt
import pytest

from app.db import _connect


# ── Helpers ───────────────────────────────────────────────────────────────────

def _register(client, email="user@example.com", password="password123"):
    with patch("app.email_report.send_confirmation_email"):
        return client.post("/api/auth/register", json={"email": email, "password": password})


def _confirm(client, flask_app):
    with _connect(flask_app) as conn:
        row = conn.execute("SELECT token FROM email_confirmation_tokens LIMIT 1").fetchone()
    assert row, "No confirmation token found"
    client.get(f"/api/auth/confirm/{row[0]}")


def _login(client, email="user@example.com", password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


@pytest.fixture
def confirmed_user(client, flask_app):
    _register(client)
    _confirm(client, flask_app)
    return {"email": "user@example.com", "password": "password123"}


@pytest.fixture
def auth_token(client, confirmed_user):
    resp = _login(client)
    return resp.get_json()["token"]


# ── POST /api/auth/register ───────────────────────────────────────────────────

class TestRegister:
    def test_success_returns_201(self, client):
        resp = _register(client)
        assert resp.status_code == 201
        assert "Check your email" in resp.get_json()["message"]

    def test_creates_unconfirmed_user(self, client, flask_app):
        _register(client)
        with _connect(flask_app) as conn:
            user = conn.execute("SELECT is_confirmed FROM users WHERE email = 'user@example.com'").fetchone()
        assert user is not None
        assert user[0] == 0

    def test_sends_confirmation_email(self, client):
        with patch("app.email_report.send_confirmation_email") as mock_send:
            client.post("/api/auth/register", json={"email": "user@example.com", "password": "password123"})
        mock_send.assert_called_once()

    def test_email_normalized_to_lowercase(self, client, flask_app):
        with patch("app.email_report.send_confirmation_email"):
            client.post("/api/auth/register", json={"email": "USER@EXAMPLE.COM", "password": "password123"})
        with _connect(flask_app) as conn:
            row = conn.execute("SELECT email FROM users WHERE email = 'user@example.com'").fetchone()
        assert row is not None

    def test_invalid_email_returns_400(self, client):
        with patch("app.email_report.send_confirmation_email"):
            resp = client.post("/api/auth/register", json={"email": "not-an-email", "password": "password123"})
        assert resp.status_code == 400

    def test_short_password_returns_400(self, client):
        with patch("app.email_report.send_confirmation_email"):
            resp = client.post("/api/auth/register", json={"email": "user@example.com", "password": "short"})
        assert resp.status_code == 400

    def test_duplicate_email_returns_409(self, client):
        _register(client)
        resp = _register(client)
        assert resp.status_code == 409

    def test_email_failure_still_returns_201(self, client):
        with patch("app.email_report.send_confirmation_email", side_effect=RuntimeError("SMTP error")):
            resp = client.post("/api/auth/register", json={"email": "user@example.com", "password": "password123"})
        assert resp.status_code == 201


# ── GET /api/auth/confirm/<token> ─────────────────────────────────────────────

class TestConfirm:
    def test_valid_token_redirects(self, client, flask_app):
        _register(client)
        with _connect(flask_app) as conn:
            token = conn.execute("SELECT token FROM email_confirmation_tokens LIMIT 1").fetchone()[0]
        resp = client.get(f"/api/auth/confirm/{token}")
        assert resp.status_code == 302
        assert "confirmed=1" in resp.headers["Location"]

    def test_valid_token_marks_user_confirmed(self, client, flask_app):
        _register(client)
        _confirm(client, flask_app)
        with _connect(flask_app) as conn:
            user = conn.execute("SELECT is_confirmed FROM users WHERE email = 'user@example.com'").fetchone()
        assert user[0] == 1

    def test_valid_token_deleted_after_use(self, client, flask_app):
        _register(client)
        _confirm(client, flask_app)
        with _connect(flask_app) as conn:
            count = conn.execute("SELECT COUNT(*) FROM email_confirmation_tokens").fetchone()[0]
        assert count == 0

    def test_invalid_token_returns_404(self, client):
        resp = client.get("/api/auth/confirm/nonexistent-token")
        assert resp.status_code == 404

    def test_expired_token_returns_410(self, client, flask_app):
        _register(client)
        expired = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        with _connect(flask_app) as conn:
            token = conn.execute("SELECT token FROM email_confirmation_tokens LIMIT 1").fetchone()[0]
            conn.execute("UPDATE email_confirmation_tokens SET expires_at = ?", (expired,))
        resp = client.get(f"/api/auth/confirm/{token}")
        assert resp.status_code == 410

    def test_token_cannot_be_reused(self, client, flask_app):
        _register(client)
        with _connect(flask_app) as conn:
            token = conn.execute("SELECT token FROM email_confirmation_tokens LIMIT 1").fetchone()[0]
        client.get(f"/api/auth/confirm/{token}")
        resp = client.get(f"/api/auth/confirm/{token}")
        assert resp.status_code == 404


# ── POST /api/auth/login ──────────────────────────────────────────────────────

class TestLogin:
    def test_success_returns_token_and_email(self, client, confirmed_user):
        resp = _login(client)
        assert resp.status_code == 200
        data = resp.get_json()
        assert "token" in data
        assert data["email"] == confirmed_user["email"]

    def test_wrong_password_returns_401(self, client, confirmed_user):
        resp = _login(client, password="wrongpassword")
        assert resp.status_code == 401

    def test_unknown_email_returns_401(self, client):
        resp = _login(client, email="nobody@example.com")
        assert resp.status_code == 401

    def test_unconfirmed_account_returns_403(self, client):
        _register(client)
        resp = _login(client)
        assert resp.status_code == 403

    def test_token_is_valid_jwt(self, client, confirmed_user, flask_app):
        resp = _login(client)
        token = resp.get_json()["token"]
        payload = jwt.decode(token, flask_app.config["SECRET_KEY"], algorithms=["HS256"])
        assert payload["email"] == confirmed_user["email"]


# ── GET /api/auth/me ──────────────────────────────────────────────────────────

class TestMe:
    def test_valid_token_returns_user(self, client, confirmed_user, auth_token):
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {auth_token}"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["email"] == confirmed_user["email"]
        assert data["is_confirmed"] is True

    def test_no_token_returns_401(self, client):
        resp = client.get("/api/auth/me")
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Missing token"

    def test_invalid_token_returns_401(self, client):
        resp = client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Invalid token"

    def test_expired_token_returns_401(self, client, confirmed_user, flask_app):
        expired_token = jwt.encode(
            {
                "sub": "1",
                "email": confirmed_user["email"],
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            },
            flask_app.config["SECRET_KEY"],
            algorithm="HS256",
        )
        resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        assert resp.status_code == 401
        assert resp.get_json()["error"] == "Token expired"

    def test_missing_bearer_prefix_returns_401(self, client, auth_token):
        resp = client.get("/api/auth/me", headers={"Authorization": auth_token})
        assert resp.status_code == 401
