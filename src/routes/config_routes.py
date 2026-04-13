"""Global configuration routes."""
from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.extensions import db
from src.models.models import GlobalConfig
from src.schemas import ConfigUpdate
from src.services.auth import cognito_token_required

config_bp = Blueprint("config", __name__, url_prefix="/api/config")


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
    """Update a configuration setting.
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
    responses:
      200:
        description: Configuration updated
    """
    try:
        data = ConfigUpdate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    cfg = GlobalConfig.query.filter_by(key=key).first()
    if not cfg:
        return jsonify({"error": "Configuration key not found"}), 404

    cfg.value = data.value
    db.session.commit()
    return jsonify({"key": cfg.key, "value": cfg.value, "description": cfg.description})
