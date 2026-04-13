"""Game flow routes — player-facing APIs for the game lifecycle."""
import random
from datetime import datetime, timezone

import requests as http_requests
from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from src.extensions import db, limiter
from src.models.models import Event, Game, GamePlayer, GamePlayerAnswer, GameQuestion, GlobalConfig, Player, QuestionDifficulty
from src.schemas import GameEnd, PlayerCreate
from src.services.auth import generate_player_token, player_session_required

BUILDER_PROFILE_API = "https://api.builder.aws.com/ums/getProfileByAlias"

game_bp = Blueprint("games", __name__, url_prefix="/api/game")

GAME_QUESTION_COUNT = 32


def _serialize_player(player):
    return {
        "id": player.id,
        "name": player.name,
        "avatar": player.avatar,
        "preferred_coding_language": player.preferred_coding_language,
        "difficulty": player.difficulty.value,
        "created_at": player.created_at.isoformat(),
    }


def _serialize_game_player(gp):
    return {
        "game_id": gp.game_id,
        "player_id": gp.player_id,
        "score": gp.score,
        "time_taken_seconds": gp.time_taken_seconds,
        "completed_at": gp.completed_at.isoformat() if gp.completed_at else None,
        "joined_at": gp.joined_at.isoformat(),
    }


# --- Validate builder.aws.com alias ---

@game_bp.route("/validate-builder-alias", methods=["POST"])
@limiter.limit("15 per minute")
def validate_builder_alias():
    """Check whether an alias exists on builder.aws.com.
    ---
    tags:
      - Game Flow
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - alias
          properties:
            alias:
              type: string
              description: The builder.aws.com alias (without the @ prefix)
    responses:
      200:
        description: Alias validation result
        schema:
          type: object
          properties:
            valid:
              type: boolean
      400:
        description: Missing alias
    """
    body = request.get_json() or {}
    alias = body.get("alias", "").strip()
    if not alias:
        return jsonify({"error": "alias is required"}), 400

    # Check if builder alias validation is enabled
    cfg = GlobalConfig.query.filter_by(key=GlobalConfig.REQUIRE_BUILDER_ALIAS).first()
    if not cfg or cfg.value.lower() != "true":
        return jsonify({"valid": True, "enabled": False})

    # Strip leading @ if the user included it
    if alias.startswith("@"):
        alias = alias[1:]

    try:
        resp = http_requests.post(
            BUILDER_PROFILE_API,
            json={"alias": alias},
            headers={
                "Content-Type": "application/json",
                "builder-session-token": "dummy",
            },
            timeout=5,
        )
        return jsonify({"valid": resp.status_code == 200, "enabled": True})
    except http_requests.RequestException:
        # If the external service is unreachable, don't block the user
        return jsonify({"valid": True, "enabled": True})


# --- Join event via access code ---

@game_bp.route("/join", methods=["POST"])
@limiter.limit("10 per minute")
def join_event():
    """Join an event using its access code. Returns the event details and welcome text.
    ---
    tags:
      - Game Flow
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - access_code
          properties:
            access_code:
              type: string
              description: 8-character event access code (case-sensitive)
    responses:
      200:
        description: Event details for the player
        schema:
          type: object
          properties:
            event_id:
              type: integer
            event_name:
              type: string
            theme:
              type: string
            custom_welcome_text:
              type: string
            question_bank_name:
              type: string
      404:
        description: Invalid access code
    """
    body = request.get_json() or {}
    access_code = body.get("access_code", "").strip()
    if not access_code:
        return jsonify({"error": "access_code is required"}), 400

    event = Event.query.filter_by(access_code=access_code).first()
    if not event:
        return jsonify({"error": "Invalid access code"}), 404

    if event.code_expiry:
        expiry = event.code_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > expiry:
            return jsonify({"error": "This event code has expired"}), 410

    return jsonify({
        "event_id": event.id,
        "event_name": event.name,
        "theme": event.theme,
        "custom_welcome_text": event.custom_welcome_text,
        "question_bank_name": event.question_bank.name if event.question_bank else None,
        "survey_link": event.survey_link,
    })


# --- Create player profile ---

@game_bp.route("/players", methods=["POST"])
def create_player():
    """Create a new player profile.
    ---
    tags:
      - Game Flow
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - name
            - avatar
            - preferred_coding_language
            - difficulty
          properties:
            name:
              type: string
            avatar:
              type: string
              description: Chosen avatar identifier
            preferred_coding_language:
              type: string
              description: Preferred programming language
            difficulty:
              type: string
              enum: [Easy, Moderate, Hard]
    responses:
      201:
        description: Player profile created
        schema:
          type: object
          properties:
            id:
              type: integer
            name:
              type: string
            avatar:
              type: string
            preferred_coding_language:
              type: string
            difficulty:
              type: string
            created_at:
              type: string
              format: date-time
      400:
        description: Validation error
    """
    try:
        data = PlayerCreate(**request.get_json())
    except ValidationError as e:
        return jsonify({"error": e.errors()}), 400

    player = Player(
        name=data.name,
        avatar=data.avatar,
        preferred_coding_language=data.preferred_coding_language,
        difficulty=QuestionDifficulty(data.difficulty),
    )
    db.session.add(player)
    db.session.commit()

    # Issue a player session token bound to this player_id
    session_token = generate_player_token(player_id=player.id)
    result = _serialize_player(player)
    result["session_token"] = session_token

    return jsonify(result), 201


# --- Start a new game ---

@game_bp.route("/start", methods=["POST"])
@player_session_required
def start_game():
    """Start a new game for a player within an event. Selects questions from the event's question bank and creates a GamePlayer entry with score 0.
    ---
    tags:
      - Game Flow
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - event_id
            - player_id
          properties:
            event_id:
              type: integer
              description: The event to play in
            player_id:
              type: integer
              description: The player starting the game
    responses:
      201:
        description: Game started
        schema:
          type: object
          properties:
            game_id:
              type: integer
            event_id:
              type: integer
            player_id:
              type: integer
            question_count:
              type: integer
              description: Number of questions selected for this game
            questions:
              type: array
              description: Ordered list of question IDs for this game
              items:
                type: object
                properties:
                  question_id:
                    type: integer
                  question_order:
                    type: integer
      400:
        description: Validation error or no questions in bank
      404:
        description: Event or player not found
    """
    body = request.get_json() or {}
    event_id = body.get("event_id")
    player_id = body.get("player_id")

    if not event_id or not player_id:
        return jsonify({"error": "event_id and player_id are required"}), 400

    # Verify player_id matches the session token
    if player_id != request.token_player_id:
        return jsonify({"error": "player_id does not match session"}), 403

    event = Event.query.get(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404

    player = Player.query.get(player_id)
    if not player:
        return jsonify({"error": "Player not found"}), 404

    bank = event.question_bank
    if not bank or not bank.questions:
        return jsonify({"error": "No questions available in the event's question bank"}), 400

    # Select up to GAME_QUESTION_COUNT questions, randomised
    available = list(bank.questions)
    selected = random.sample(available, min(len(available), GAME_QUESTION_COUNT))

    # Create the game
    game = Game(event_id=event.id, question_bank_id=bank.id)
    db.session.add(game)
    db.session.flush()

    # Assign questions in order
    for order, q in enumerate(selected, start=1):
        gq = GameQuestion(game_id=game.id, question_id=q.id, question_order=order)
        db.session.add(gq)

    # Add player to game with score 0
    gp = GamePlayer(game_id=game.id, player_id=player.id, score=0)
    db.session.add(gp)
    db.session.commit()

    return jsonify({
        "game_id": game.id,
        "event_id": event.id,
        "player_id": player.id,
        "question_count": len(selected),
        "questions": [
            {"question_id": gq.question_id, "question_order": gq.question_order}
            for gq in game.game_questions
        ],
    }), 201


# --- End a game ---

@game_bp.route("/<int:game_id>/end", methods=["POST"])
@player_session_required
def end_game(game_id):
    """End a game for a player. Score is computed server-side from recorded answers.
    ---
    tags:
      - Game Flow
    parameters:
      - name: game_id
        in: path
        type: integer
        required: true
        description: Game ID
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - player_id
          properties:
            player_id:
              type: integer
              description: The player ending the game
    responses:
      200:
        description: Game ended, score recorded
        schema:
          type: object
          properties:
            game_id:
              type: integer
            player_id:
              type: integer
            score:
              type: integer
            time_taken_seconds:
              type: integer
            completed_at:
              type: string
              format: date-time
      404:
        description: Game or player not found in this game
    """
    body = request.get_json() or {}
    player_id = body.get("player_id")

    if not player_id:
        return jsonify({"error": "player_id is required"}), 400

    # Verify player_id matches the session token
    if player_id != request.token_player_id:
        return jsonify({"error": "player_id does not match session"}), 403

    game = Game.query.get(game_id)
    if not game:
        return jsonify({"error": "Game not found"}), 404

    gp = GamePlayer.query.filter_by(game_id=game_id, player_id=player_id).first()
    if not gp:
        return jsonify({"error": "Player not found in this game"}), 404

    if gp.completed_at:
        return jsonify({"error": "Game already ended for this player"}), 409

    # Compute score server-side from recorded answers
    score = _compute_score(gp)

    now = datetime.now(timezone.utc)
    gp.score = score
    # Ensure joined_at is timezone-aware for subtraction (SQLite stores naive datetimes)
    joined_at = gp.joined_at if gp.joined_at.tzinfo else gp.joined_at.replace(tzinfo=timezone.utc)
    gp.time_taken_seconds = int((now - joined_at).total_seconds())
    gp.completed_at = now
    db.session.commit()

    return jsonify({
        "game_id": game_id,
        "player_id": player_id,
        "score": gp.score,
        "time_taken_seconds": gp.time_taken_seconds,
        "completed_at": gp.completed_at.isoformat(),
    })


# Points per difficulty level (must match frontend POINTS_BY_DIFFICULTY)
_POINTS = {
    QuestionDifficulty.Easy: 10,
    QuestionDifficulty.Moderate: 25,
    QuestionDifficulty.Hard: 50,
}


def _compute_score(gp):
    """Compute a player's score from their recorded answers.

    Scoring rules (matching frontend):
    - Easy: 10 pts, Moderate: 25 pts, Hard: 50 pts
    - Streak multiplier: 2x after 3+ consecutive correct answers
    """
    answers = (
        GamePlayerAnswer.query
        .filter_by(game_player_id=gp.id)
        .order_by(GamePlayerAnswer.answered_at)
        .all()
    )

    score = 0
    streak = 0

    for ans in answers:
        if ans.correct:
            streak += 1
            base = _POINTS.get(ans.question.difficulty, 10)
            multiplier = 2 if streak >= 3 else 1
            score += base * multiplier
        else:
            streak = 0

    return score



# --- Player GET APIs ---

@game_bp.route("/players/<int:player_id>", methods=["GET"])
@player_session_required
def get_player(player_id):
    """Get a player profile by ID.
    ---
    tags:
      - Game Flow
    security:
      - Bearer: []
    parameters:
      - name: player_id
        in: path
        type: integer
        required: true
        description: Player ID
    responses:
      200:
        description: Player profile
      403:
        description: Player ID does not match session
      404:
        description: Player not found
    """
    if player_id != request.token_player_id:
        return jsonify({"error": "player_id does not match session"}), 403

    player = Player.query.get_or_404(player_id)
    return jsonify(_serialize_player(player))


@game_bp.route("/players/<int:player_id>/events", methods=["GET"])
@player_session_required
def get_player_events(player_id):
    """Get all events a player has participated in, with their game results.
    ---
    tags:
      - Game Flow
    security:
      - Bearer: []
    parameters:
      - name: player_id
        in: path
        type: integer
        required: true
        description: Player ID
    responses:
      200:
        description: List of events the player has participated in
      403:
        description: Player ID does not match session
      404:
        description: Player not found
    """
    if player_id != request.token_player_id:
        return jsonify({"error": "player_id does not match session"}), 403

    player = Player.query.get_or_404(player_id)
    game_players = GamePlayer.query.filter_by(player_id=player.id).all()

    results = []
    for gp in game_players:
        game = Game.query.get(gp.game_id)
        event = Event.query.get(game.event_id) if game else None
        if event:
            results.append({
                "event_id": event.id,
                "event_name": event.name,
                "theme": event.theme,
                "game_id": gp.game_id,
                "score": gp.score,
                "time_taken_seconds": gp.time_taken_seconds,
                "completed_at": gp.completed_at.isoformat() if gp.completed_at else None,
                "joined_at": gp.joined_at.isoformat(),
            })

    return jsonify(results)


# --- Leaderboard APIs ---

@game_bp.route("/leaderboard/<int:event_id>", methods=["GET"])
def event_leaderboard(event_id):
    """Get the top 10 leaderboard for a specific event.
    ---
    tags:
      - Leaderboard
    parameters:
      - name: event_id
        in: path
        type: integer
        required: true
    responses:
      200:
        description: Event info and top 10 players
      404:
        description: Event not found
    """
    event = Event.query.get_or_404(event_id)

    # Find all completed game_players for games in this event
    results = (
        db.session.query(GamePlayer, Player, Game)
        .join(Game, GamePlayer.game_id == Game.id)
        .join(Player, GamePlayer.player_id == Player.id)
        .filter(Game.event_id == event_id)
        .filter(GamePlayer.completed_at.isnot(None))
        .order_by(GamePlayer.score.desc(), GamePlayer.time_taken_seconds.asc())
        .limit(10)
        .all()
    )

    return jsonify({
        "event": {
            "id": event.id,
            "name": event.name,
            "access_code": event.access_code,
        },
        "leaderboard": [
            {
                "player_name": player.name,
                "avatar": player.avatar,
                "score": gp.score,
                "time_taken_seconds": gp.time_taken_seconds,
                "completed_at": gp.completed_at.isoformat() if gp.completed_at else None,
            }
            for gp, player, game in results
        ],
    })


@game_bp.route("/leaderboard", methods=["GET"])
def global_leaderboard():
    """Get the top 10 global leaderboard across all events.
    ---
    tags:
      - Leaderboard
    responses:
      200:
        description: Top 10 players across all events
    """
    results = (
        db.session.query(GamePlayer, Player, Game, Event)
        .join(Game, GamePlayer.game_id == Game.id)
        .join(Player, GamePlayer.player_id == Player.id)
        .join(Event, Game.event_id == Event.id)
        .filter(GamePlayer.completed_at.isnot(None))
        .order_by(GamePlayer.score.desc(), GamePlayer.time_taken_seconds.asc())
        .limit(10)
        .all()
    )

    return jsonify([
        {
            "player_name": player.name,
            "avatar": player.avatar,
            "score": gp.score,
            "time_taken_seconds": gp.time_taken_seconds,
            "completed_at": gp.completed_at.isoformat() if gp.completed_at else None,
            "event_name": event.name,
        }
        for gp, player, game, event in results
    ])


# --- Player-facing config ---

# Config keys safe to expose to players (no secrets or admin-only settings)
_PLAYER_VISIBLE_CONFIG_KEYS = {
    GlobalConfig.AUTO_PASS_ALL,
}


@game_bp.route("/config", methods=["GET"])
@limiter.limit("10 per minute")
def player_config():
    """Get player-visible configuration settings (no auth required).
    ---
    tags:
      - Game Flow
    responses:
      200:
        description: Player-visible configuration key-value pairs
        schema:
          type: object
          additionalProperties:
            type: string
    """
    configs = GlobalConfig.query.filter(
        GlobalConfig.key.in_(_PLAYER_VISIBLE_CONFIG_KEYS)
    ).all()
    return jsonify({c.key: c.value for c in configs})
