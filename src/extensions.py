from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def _get_real_ip():
    """Extract the real client IP from X-Forwarded-For (set by CloudFront)."""
    from flask import request
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2 — first is the real client
        return forwarded.split(",")[0].strip()
    return get_remote_address()


limiter = Limiter(key_func=_get_real_ip, storage_uri="memory://")
