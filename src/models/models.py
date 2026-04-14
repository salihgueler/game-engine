import enum
import secrets
import string
from datetime import datetime, timezone

from src.extensions import db


def _generate_access_code(length=8):
    """Generate a random alphanumeric access code (case-sensitive)."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


class QuestionCategory(enum.Enum):
    Coding = "Coding"
    General = "General"
    MultipleChoice = "MultipleChoice"


class QuestionDifficulty(enum.Enum):
    Easy = "Easy"
    Moderate = "Moderate"
    Hard = "Hard"


# Many-to-many association table: QuestionBank <-> Question
question_bank_questions = db.Table(
    "question_bank_questions",
    db.Column("id", db.Integer, primary_key=True, autoincrement=True),
    db.Column("question_bank_id", db.Integer, db.ForeignKey("question_banks.id"), nullable=False),
    db.Column("question_id", db.Integer, db.ForeignKey("questions.id"), nullable=False),
    db.UniqueConstraint("question_bank_id", "question_id", name="uq_bank_question_assignment"),
)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    access_code = db.Column(db.String(8), nullable=False, unique=True, default=_generate_access_code)
    question_bank_id = db.Column(db.Integer, db.ForeignKey("question_banks.id"), nullable=False)
    theme = db.Column(db.String(128), nullable=False)
    custom_welcome_text = db.Column(db.Text, nullable=True)
    survey_link = db.Column(db.Text, nullable=True)
    code_expiry = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    games = db.relationship("Game", backref="event", lazy=True, cascade="all, delete-orphan")
    question_bank = db.relationship("QuestionBank", backref="events", lazy=True)


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False)
    avatar = db.Column(db.String(128), nullable=False)
    preferred_coding_language = db.Column(db.String(64), nullable=False)
    difficulty = db.Column(db.Enum(QuestionDifficulty), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class QuestionBank(db.Model):
    __tablename__ = "question_banks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    # Many-to-many: a bank has many questions, a question can be in many banks
    questions = db.relationship("Question", secondary=question_bank_questions, backref=db.backref("question_banks", lazy=True), lazy=True)
    games = db.relationship("Game", backref="question_bank", lazy=True, cascade="all, delete-orphan")


class Question(db.Model):
    """Independent question entity. Can be assigned to zero, one, or many QuestionBanks."""
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question_number = db.Column(db.Integer, nullable=False, unique=True)
    category = db.Column(db.Enum(QuestionCategory), nullable=False)
    difficulty = db.Column(db.Enum(QuestionDifficulty), nullable=False)
    description = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    hint = db.Column(db.Text, nullable=True)
    # Multiple choice options stored as JSON string
    options = db.Column(db.Text, nullable=True)
    # Coding question fields
    code_programming_language = db.Column(db.String(64), nullable=True)
    code_sample_input = db.Column(db.Text, nullable=True)
    code_sample_output = db.Column(db.Text, nullable=True)
    code_hidden_input = db.Column(db.Text, nullable=True)
    code_hidden_output = db.Column(db.Text, nullable=True)
    # Stats
    times_passed = db.Column(db.Integer, nullable=False, default=0)
    times_hint_used = db.Column(db.Integer, nullable=False, default=0)
    times_incorrect = db.Column(db.Integer, nullable=False, default=0)
    times_correct = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Game(db.Model):
    __tablename__ = "games"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    question_bank_id = db.Column(db.Integer, db.ForeignKey("question_banks.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    game_questions = db.relationship("GameQuestion", backref="game", lazy=True, cascade="all, delete-orphan")
    game_players = db.relationship("GamePlayer", backref="game", lazy=True, cascade="all, delete-orphan")


class GameQuestion(db.Model):
    __tablename__ = "game_questions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    question_order = db.Column(db.Integer, nullable=False)

    __table_args__ = (db.UniqueConstraint("game_id", "question_id", name="uq_game_question"),)


class GamePlayer(db.Model):
    __tablename__ = "game_players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_id = db.Column(db.Integer, db.ForeignKey("games.id"), nullable=False)
    player_id = db.Column(db.Integer, db.ForeignKey("players.id"), nullable=False)
    score = db.Column(db.Integer, nullable=False, default=0)
    time_taken_seconds = db.Column(db.Integer, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    joined_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    answers = db.relationship("GamePlayerAnswer", backref="game_player", lazy=True, cascade="all, delete-orphan")

    __table_args__ = (db.UniqueConstraint("game_id", "player_id", name="uq_game_player"),)


class GamePlayerAnswer(db.Model):
    """Tracks each answer submission per game/player/question for server-side scoring."""
    __tablename__ = "game_player_answers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    game_player_id = db.Column(db.Integer, db.ForeignKey("game_players.id"), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey("questions.id"), nullable=False)
    correct = db.Column(db.Boolean, nullable=False)
    tile_difficulty = db.Column(db.String(16), nullable=True)
    answered_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    question = db.relationship("Question", lazy=True)

    __table_args__ = (db.UniqueConstraint("game_player_id", "question_id", name="uq_game_player_answer"),)


class GlobalConfig(db.Model):
    """Global configuration settings for the question engine."""
    __tablename__ = "global_config"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    key = db.Column(db.String(128), nullable=False, unique=True)
    value = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)

    # Default config keys
    SHOW_CORRECT_ON_WRONG = "show_correct_answer_on_wrong"
    AUTO_PASS_ALL = "auto_pass_all_questions"
    REQUIRE_BUILDER_ALIAS = "require_builder_alias"


class AuditLog(db.Model):
    """Audit log for tracking admin and game actions."""
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    actor = db.Column(db.String(256), nullable=False)
    action = db.Column(db.String(64), nullable=False, index=True)
    resource_type = db.Column(db.String(64), nullable=False)
    resource_id = db.Column(db.String(128), nullable=True)
    details = db.Column(db.Text, nullable=True)
