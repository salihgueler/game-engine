"""JWT authentication service with daily token generation and auto-refresh."""
import functools
import hashlib
import time
from datetime import datetime, timedelta, timezone

import jwt
from flask import current_app, jsonify, request


def _get_daily_seed():
    """Generate a deterministic daily seed for token generation."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    secret = current_app.config["SECRET_KEY"]
    return hashlib.sha256(f"{secret}:{today}".encode()).hexdigest()


def generate_token():
    """Generate a JWT token valid for 24 hours, seeded daily."""
    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "exp": now + current_app.config["JWT_EXPIRATION"],
        "sub": "quest-admin",
        "daily_seed": _get_daily_seed(),
    }
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm=current_app.config["JWT_ALGORITHM"])


def decode_token(token):
    """Decode and validate a JWT token."""
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=[current_app.config["JWT_ALGORITHM"]])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def token_required(f):
    """Decorator to require a valid JWT token for API endpoints."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        token = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        payload = decode_token(token)
        if payload is None:
            return jsonify({"error": "Token is invalid or expired"}), 401

        # Auto-refresh: if token expires within 1 hour, issue a new one
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        if exp - datetime.now(timezone.utc) < timedelta(hours=1):
            new_token = generate_token()
            # Attach refreshed token to response headers
            request._refreshed_token = new_token

        return f(*args, **kwargs)
    return decorated


def add_refresh_header(response):
    """After-request handler to add refreshed token header if applicable."""
    refreshed = getattr(request, "_refreshed_token", None)
    if refreshed:
        response.headers["X-Refreshed-Token"] = refreshed
    return response
