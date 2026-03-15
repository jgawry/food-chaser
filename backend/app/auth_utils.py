"""JWT helpers and require_auth decorator."""
import functools
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app, g, jsonify, request


def make_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def decode_token(token_str: str) -> dict:
    return jwt.decode(token_str, current_app.config["SECRET_KEY"], algorithms=["HS256"])


def require_auth(f):
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing token"}), 401
        token_str = auth_header[len("Bearer "):]
        try:
            payload = decode_token(token_str)
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        g.current_user_id = int(payload["sub"])
        g.current_user_email = payload["email"]
        return f(*args, **kwargs)
    return wrapper
