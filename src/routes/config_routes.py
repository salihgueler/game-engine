"""Global configuration routes with audit logging."""
import logging

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.extensions import db
from src.models.models import GlobalConfig
from src.schemas import ConfigUpdate
from src.services.auth import cognito_token_required

logger = logging.getLogger(__name__)

config_bp = Blueprint("config", __name__, url_prefix="/api/config")

# Keys that require explicit confirmation to change
_DANGEROUS_KEYS = {
    GlobalConfig.AUTO_PASS_ALL,
}


@config_bp.route("", methods=["GET"])
@cognito_token_required
def get_all_config():
    """Get all global configuration settings.
    ---
    tags:
      - Configuration
    security:
      - Bearer: []
    responses:
      200:
        description: List of configuration settings
    """
    configs = GlobalConfig.query.all()
    return jsonify([
        {"key": c.key, "value": c.value, "description": c.description}
        for c in configs
    ])


@config_bp.route("/<string:key>", methods=["PUT"])
@cognito_token_required
def update_config(key):
    """Update a configuration setting. Dangerous keys require confirm=true.
    ---
    tags:
      - Configuration
    security:
      - Bearer: []
    parameters:
      - name: key
        in: path
        type: string
        required: true
      - name: body
        in: body
        schema:
          type: object
          properties:
            value:
              type: string
            confirm:
              type: boolean
              description: Required for dangerous config keys
    responses:
      200:
        description: Configuration updated
      400:
        description: Validation error
      404:
        description: Configuration key not found
      409:
        description: Confirmation required for dangerous key
    """
    body = request.get_json() or {}

    try:
        data = ConfigUpdate(**body)
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    cfg = GlobalConfig.query.filter_by(key=key).first()
    if not cfg:
        return jsonify({"error": "Configuration key not found"}), 404

    # Require explicit confirmation for dangerous keys
    if key in _DANGEROUS_KEYS and not body.get("confirm"):
        return jsonify({
            "error": f"Changing '{key}' is a dangerous operation. Send confirm=true to proceed.",
            "requires_confirmation": True,
        }), 409

    old_value = cfg.value
    cfg.value = data.value
    db.session.commit()

    # Audit log
    admin_user = getattr(request, "cognito_user", "unknown")
    logger.warning(
        "CONFIG_CHANGE: user=%s key=%s old_value=%s new_value=%s",
        admin_user, key, old_value, data.value,
    )

    # Record in audit log table
    from src.services.audit import log_action
    log_action("config_change", "config", key, {"old_value": old_value, "new_value": data.value})

    return jsonify({"key": cfg.key, "value": cfg.value, "description": cfg.description})
