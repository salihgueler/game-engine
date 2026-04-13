"""Audit logging service — records admin and game actions to the database."""
import json
import logging

from flask import request

from src.extensions import db
from src.models.models import AuditLog

logger = logging.getLogger(__name__)


def log_action(action: str, resource_type: str, resource_id: str | None = None, details: dict | None = None):
    """Record an audit log entry.

    Args:
        action: e.g. "create", "update", "delete", "login", "config_change", "game_end"
        resource_type: e.g. "event", "question", "config", "game", "player"
        resource_id: ID of the affected resource (optional)
        details: Additional context as a dict (optional)
    """
    actor = getattr(request, "cognito_user", None) or "system"

    entry = AuditLog(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details=json.dumps(details) if details else None,
    )
    db.session.add(entry)
    db.session.commit()

    logger.info(
        "AUDIT: actor=%s action=%s resource=%s/%s",
        actor, action, resource_type, resource_id,
    )
