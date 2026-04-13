"""Authentication routes.

The admin token endpoint has been removed — admin auth is now handled by
Amazon Cognito. Only the player-facing token endpoint remains.
"""
from flask import Blueprint, jsonify

from src.extensions import limiter
from src.services.auth import generate_player_token

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@auth_bp.route("/token", methods=["POST"])
@limiter.limit("10 per minute")
def get_player_token():
    """Generate a player-facing JWT token for game-play API access.
    ---
    tags:
      - Authentication
    responses:
      200:
        description: Player JWT token generated
        schema:
          type: object
          properties:
            token:
              type: string
    """
    token = generate_player_token()
    return jsonify({"token": token})
