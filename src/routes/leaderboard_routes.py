"""Admin leaderboard routes — view and manage leaderboard entries."""
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from src.extensions import db
from src.models.models import Event, Game, GamePlayer, Player, QuestionDifficulty
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


@leaderboard_bp.route("/entry/<int:game_player_id>", methods=["PATCH"])
@cognito_token_required
def update_leaderboard_entry(game_player_id):
    """Update a player's score on the leaderboard.
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
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - score
          properties:
            score:
              type: integer
              description: New score value
    responses:
      200:
        description: Score updated
      400:
        description: Invalid input
      404:
        description: Entry not found
    """
    gp = GamePlayer.query.get_or_404(game_player_id)
    body = request.get_json() or {}
    new_score = body.get("score")

    if new_score is None or not isinstance(new_score, int) or new_score < 0:
        return jsonify({"error": "score must be a non-negative integer"}), 400

    player = Player.query.get(gp.player_id)
    player_name = player.name if player else "unknown"

    log_action("leaderboard_update_score", "game_player", game_player_id, {
        "player_name": player_name,
        "old_score": gp.score,
        "new_score": new_score,
    })

    gp.score = new_score
    db.session.commit()

    return jsonify({
        "game_player_id": gp.id,
        "player_name": player_name,
        "score": gp.score,
    })


@leaderboard_bp.route("/entry", methods=["POST"])
@cognito_token_required
def add_leaderboard_entry():
    """Add a player to the leaderboard for a specific event.
    ---
    tags:
      - Admin Leaderboard
    security:
      - Bearer: []
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - event_id
            - player_name
            - score
          properties:
            event_id:
              type: integer
            player_name:
              type: string
            avatar:
              type: string
              default: "🏴‍☠️"
            score:
              type: integer
    responses:
      201:
        description: Entry added to leaderboard
      400:
        description: Invalid input
      404:
        description: Event not found
    """
    body = request.get_json() or {}
    event_id = body.get("event_id")
    player_name = body.get("player_name", "").strip()
    avatar = body.get("avatar", "🏴\u200d☠️")
    score = body.get("score")

    if not event_id or not player_name or score is None:
        return jsonify({"error": "event_id, player_name, and score are required"}), 400
    if not isinstance(score, int) or score < 0:
        return jsonify({"error": "score must be a non-negative integer"}), 400

    event = Event.query.get_or_404(event_id)

    # Find or pick a game in this event
    game = Game.query.filter_by(event_id=event.id).first()
    if not game:
        return jsonify({"error": "No games exist for this event"}), 400

    # Create a player record
    player = Player(
        name=player_name,
        avatar=avatar,
        preferred_coding_language="python",
        difficulty=QuestionDifficulty.Moderate,
    )
    db.session.add(player)
    db.session.flush()

    now = datetime.now(timezone.utc)
    gp = GamePlayer(
        game_id=game.id,
        player_id=player.id,
        score=score,
        completed_at=now,
        joined_at=now,
    )
    db.session.add(gp)

    log_action("leaderboard_add", "game_player", None, {
        "player_name": player_name,
        "score": score,
        "event_id": event.id,
        "event_name": event.name,
    })

    db.session.commit()

    return jsonify({
        "game_player_id": gp.id,
        "player_id": player.id,
        "player_name": player_name,
        "avatar": avatar,
        "score": score,
        "event_id": event.id,
    }), 201
