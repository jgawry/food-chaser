"""Authentication routes: register, confirm, login, me."""
import re
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from flask import Blueprint, current_app, g, jsonify, redirect, request
from flask_bcrypt import Bcrypt

from ..auth_utils import make_token, require_auth
from ..db import _connect
from ..extensions import limiter

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")
bcrypt = Bcrypt()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@auth_bp.record_once
def _init_bcrypt(state):
    bcrypt.init_app(state.app)


# ── Register ──────────────────────────────────────────────────────

@auth_bp.route("/register", methods=["POST"])
@limiter.limit("5 per hour")
def register():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not _EMAIL_RE.match(email):
        return jsonify({"error": "Invalid email"}), 400
    if len(password) < 8:
        return jsonify({"error": "Password must be at least 8 characters"}), 400

    pw_hash = bcrypt.generate_password_hash(password).decode("utf-8")
    now = datetime.now(timezone.utc).isoformat()

    try:
        with _connect(current_app) as conn:
            cur = conn.execute(
                "INSERT INTO users (email, password_hash, is_confirmed, created_at) VALUES (?, ?, 0, ?)",
                (email, pw_hash, now),
            )
            user_id = cur.lastrowid
    except sqlite3.IntegrityError:
        return jsonify({"error": "Email already registered"}), 409

    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    with _connect(current_app) as conn:
        conn.execute(
            "INSERT INTO email_confirmation_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
            (user_id, token, expires_at),
        )

    try:
        from ..email_report import send_confirmation_email
        send_confirmation_email(email, token, current_app.config["APP_BASE_URL"])
    except Exception as exc:
        current_app.logger.error("Failed to send confirmation email: %s", exc)

    return jsonify({"message": "Registration successful. Check your email to confirm your account."}), 201


# ── Confirm ───────────────────────────────────────────────────────

@auth_bp.route("/confirm/<token>")
def confirm(token):
    now = datetime.now(timezone.utc).isoformat()
    with _connect(current_app) as conn:
        row = conn.execute(
            "SELECT id, user_id, expires_at FROM email_confirmation_tokens WHERE token = ?",
            (token,),
        ).fetchone()

    if not row:
        return jsonify({"error": "Invalid or already used confirmation link"}), 404

    token_id, user_id, expires_at = row
    if now > expires_at:
        with _connect(current_app) as conn:
            conn.execute("DELETE FROM email_confirmation_tokens WHERE id = ?", (token_id,))
        return jsonify({"error": "Confirmation link has expired. Please register again."}), 410

    with _connect(current_app) as conn:
        conn.execute("UPDATE users SET is_confirmed = 1 WHERE id = ?", (user_id,))
        conn.execute("DELETE FROM email_confirmation_tokens WHERE id = ?", (token_id,))

    return redirect("/?confirmed=1")


# ── Login ─────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["POST"])
@limiter.limit("10 per 15 minutes")
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    with _connect(current_app) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, email, password_hash, is_confirmed FROM users WHERE email = ?",
            (email,),
        ).fetchone()

    if not user or not bcrypt.check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Invalid email or password"}), 401

    if not user["is_confirmed"]:
        return jsonify({"error": "Please confirm your email before logging in"}), 403

    token = make_token(user["id"], user["email"])
    return jsonify({"token": token, "email": user["email"]}), 200


# ── Me ────────────────────────────────────────────────────────────

@auth_bp.route("/me")
@require_auth
def me():
    with _connect(current_app) as conn:
        conn.row_factory = sqlite3.Row
        user = conn.execute(
            "SELECT id, email, is_confirmed FROM users WHERE id = ?",
            (g.current_user_id,),
        ).fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"id": user["id"], "email": user["email"], "is_confirmed": bool(user["is_confirmed"])}), 200
