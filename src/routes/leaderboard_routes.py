"""Admin leaderboard routes — view and manage leaderboard entries."""
from flask import Blueprint, jsonify, request

from src.extensions import db
from src.models.models import Event, Game, GamePlayer, Player
from src.services.audit import log_action
from src.services.auth import cognito_token_required

leaderboard_bp = Blueprint("admin_leaderboard", __name__, url_prefix="/api/admin/leaderboard")


@leaderboard_bp.route("/global", methods=["GET"])
@cognito_token_required
def admin_global_leaderboard():
    """Get the full global leaderboard (no limit) for admin management.
    ---
    tags:
      - Admin Leaderboard
    security:
      - Bearer: []
    responses:
      200:
        description: All completed game entries across all events
    """
    results = (
        db.session.query(GamePlayer, Player, Game, Event)
        .join(Game, GamePlayer.game_id == Game.id)
        .join(Player, GamePlayer.player_id == Player.id)
        .join(Event, Game.event_id == Event.id)
        .filter(GamePlayer.completed_at.isnot(None))
        .order_by(GamePlayer.score.desc(), GamePlayer.time_taken_seconds.asc())
        .all()
    )

    return jsonify([
        {
            "game_player_id": gp.id,
            "game_id": gp.game_id,
            "player_id": player.id,
            "player_name": player.name,
            "avatar": player.avatar,
            "score": gp.score,
            "time_taken_seconds": gp.time_taken_seconds,
            "completed_at": gp.completed_at.isoformat() if gp.completed_at else None,
            "event_id": event.id,
            "event_name": event.name,
        }
        for gp, player, game, event in results
    ])


@leaderboard_bp.route("/event/<int:event_id>", methods=["GET"])
@cognito_token_required
def admin_event_leaderboard(event_id):
    """Get the full leaderboard for a specific event (no limit) for admin management.
    ---
    tags:
      - Admin Leaderboard
    security:
      - Bearer: []
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: All completed game entries for this event
      404:
        description: Event not found
    """
    event = Event.query.get_or_404(event_id)

    results = (
        db.session.query(GamePlayer, Player, Game)
        .join(Game, GamePlayer.game_id == Game.id)
        .join(Player, GamePlayer.player_id == Player.id)
        .filter(Game.event_id == event_id)
        .filter(GamePlayer.completed_at.isnot(None))
        .order_by(GamePlayer.score.desc(), GamePlayer.time_taken_seconds.asc())
        .all()
    )

    return jsonify([
        {
            "game_player_id": gp.id,
            "game_id": gp.game_id,
            "player_id": player.id,
            "player_name": player.name,
            "avatar": player.avatar,
            "score": gp.score,
            "time_taken_seconds": gp.time_taken_seconds,
            "completed_at": gp.completed_at.isoformat() if gp.completed_at else None,
        }
        for gp, player, game in results
    ])


@leaderboard_bp.route("/entry/<int:game_player_id>", methods=["DELETE"])
@cognito_token_required
def remove_leaderboard_entry(game_player_id):
    """Remove a player's game entry from the leaderboard by resetting their score.
    ---
    tags:
      - Admin Leaderboard
    security:
      - Bearer: []
    parameters:
      - name: game_player_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Entry removed from leaderboard
      404:
        description: Entry not found
    """
    gp = GamePlayer.query.get_or_404(game_player_id)

    player = Player.query.get(gp.player_id)
    player_name = player.name if player else "unknown"

    log_action("leaderboard_remove", "game_player", game_player_id, {
        "player_name": player_name,
        "player_id": gp.player_id,
        "game_id": gp.game_id,
        "old_score": gp.score,
    })

    # Reset score and completion — effectively removes from leaderboard
    gp.score = 0
    gp.completed_at = None
    gp.time_taken_seconds = None
    db.session.commit()

    return jsonify({"message": f"Removed {player_name} from leaderboard"})
