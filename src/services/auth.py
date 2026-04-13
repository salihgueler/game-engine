"""Cognito JWT authentication service for admin endpoints.

Validates JWTs issued by Amazon Cognito. The player-facing token endpoint
remains available for game-play APIs that don't require admin access.
"""
import functools
import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import jwt
import requests
from flask import current_app, jsonify, request

logger = logging.getLogger(__name__)

# Cache for Cognito JWKS keys
_jwks_cache: dict[str, object] = {}
_jwks_cache_time: float = 0
_JWKS_CACHE_TTL = 3600  # 1 hour


def _get_cognito_config() -> tuple[str, str, str]:
    """Return (region, user_pool_id, app_client_id) from app config."""
    region = current_app.config["COGNITO_REGION"]
    pool_id = current_app.config["COGNITO_USER_POOL_ID"]
    client_id = current_app.config["COGNITO_APP_CLIENT_ID"]
    return region, pool_id, client_id


def _get_jwks() -> dict[str, object]:
    """Fetch and cache the Cognito JWKS (JSON Web Key Set)."""
    global _jwks_cache, _jwks_cache_time

    if _jwks_cache and (time.time() - _jwks_cache_time) < _JWKS_CACHE_TTL:
        return _jwks_cache

    region, pool_id, _ = _get_cognito_config()
    jwks_url = (
        f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"
        f"/.well-known/jwks.json"
    )

    resp = requests.get(jwks_url, timeout=5)
    resp.raise_for_status()
    keys = resp.json()["keys"]

    _jwks_cache = {k["kid"]: k for k in keys}
    _jwks_cache_time = time.time()
    logger.info("Refreshed Cognito JWKS cache (%d keys)", len(_jwks_cache))
    return _jwks_cache


def _decode_cognito_token(token: str) -> dict | None:
    """Decode and validate a Cognito JWT token."""
    try:
        # Decode header to get the key ID
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            logger.warning("Token missing kid header")
            return None

        jwks = _get_jwks()
        key_data = jwks.get(kid)
        if not key_data:
            # Key not found — force refresh in case keys rotated
            _jwks_cache.clear()
            jwks = _get_jwks()
            key_data = jwks.get(kid)
            if not key_data:
                logger.warning("Token kid %s not found in JWKS", kid)
                return None

        public_key = jwt.algorithms.RSAAlgorithm.from_jwk(key_data)

        region, pool_id, client_id = _get_cognito_config()
        issuer = f"https://cognito-idp.{region}.amazonaws.com/{pool_id}"

        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=issuer,
            audience=client_id,
            options={"require": ["exp", "iss", "sub", "aud"]},
        )
        return payload

    except jwt.ExpiredSignatureError:
        logger.info("Cognito token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid Cognito token: %s", e)
        return None
    except Exception as e:
        logger.error("Cognito token validation error: %s", e)
        return None


def cognito_token_required(f):
    """Decorator to require a valid Cognito JWT for admin API endpoints."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif auth_header:
            token = auth_header

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        payload = _decode_cognito_token(token)
        if payload is None:
            return jsonify({"error": "Token is invalid or expired"}), 401

        # Store the authenticated user info on the request for audit logging
        request.cognito_user = payload.get("email") or payload.get("sub")

        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Player-facing token (kept for game-play APIs — SEC-05 will add player
# session binding later, but for now this preserves backward compatibility)
# ---------------------------------------------------------------------------

def generate_player_token():
    """Generate a simple player-facing JWT for game-play API access."""
    secret = current_app.config.get("PLAYER_TOKEN_SECRET")
    if not secret:
        raise RuntimeError("PLAYER_TOKEN_SECRET is not configured")
    now = datetime.now(timezone.utc)
    payload = {
        "iat": now,
        "exp": now + timedelta(hours=24),
        "sub": "quest-player",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_player_token(token: str) -> dict | None:
    """Decode and validate a player-facing JWT token."""
    secret = current_app.config.get("PLAYER_TOKEN_SECRET")
    if not secret:
        return None
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def player_token_required(f):
    """Decorator to require a valid player token for game-play API endpoints."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        token = None
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif auth_header:
            token = auth_header

        if not token:
            return jsonify({"error": "Token is missing"}), 401

        payload = decode_player_token(token)
        if payload is None:
            return jsonify({"error": "Token is invalid or expired"}), 401

        return f(*args, **kwargs)
    return decorated


def add_refresh_header(response):
    """After-request handler — kept for backward compatibility."""
    return response
