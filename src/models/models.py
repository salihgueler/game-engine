import enum
from datetime import datetime, timezone

from src.extensions import db


class QuestionCategory(enum.Enum):
    Coding = "Coding"
    General = "General"
    MultipleChoice = "MultipleChoice"


class QuestionDifficulty(enum.Enum):
    Easy = "Easy"
    Moderate = "Moderate"
    Hard = "Hard"


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    theme = db.Column(db.String(128), nullable=False)
    custom_welcome_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    games = db.relationship("Game", backref="event", lazy=True)


class Player(db.Model):
    __tablename__ = "players"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))


class QuestionBank(db.Model):
    __tablename__ = "question_banks"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(128), nullable=False, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    questions = db.relationship("Question", backref="question_bank", lazy=True, cascade="all, delete-orphan")
    games = db.relationship("Game", backref="question_bank", lazy=True)


class Question(db.Model):
    __tablename__ = "questions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    question_bank_id = db.Column(db.Integer, db.ForeignKey("question_banks.id"), nullable=False)
    question_number = db.Column(db.Integer, nullable=False)
    category = db.Column(db.Enum(QuestionCategory), nullable=False)
    difficulty = db.Column(db.Enum(QuestionDifficulty), nullable=False)
    description = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    hint = db.Column(db.Text, nullable=True)
    # Multiple choice options stored as JSON string
    options = db.Column(db.Text, nullable=True)
    # Coding question fields
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

    __table_args__ = (db.UniqueConstraint("question_bank_id", "question_number", name="uq_bank_question_number"),)


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
    joined_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (db.UniqueConstraint("game_id", "player_id", name="uq_game_player"),)


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
