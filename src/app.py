"""Flask application factory."""
import logging
import os

from flasgger import Swagger
from flask import Flask
from flask_cors import CORS

from src.config import config_by_name
from src.extensions import db, limiter
from src.models.models import GlobalConfig


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get("FLASK_ENV", "development")

    # Configure application logging
    log_level = os.environ.get("LOG_LEVEL", "DEBUG").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.from_object(config_by_name[config_name])

    # Extensions
    db.init_app(app)
    limiter.init_app(app)
    CORS(app, expose_headers=["X-Refreshed-Token"])

    # Swagger — only enabled in development
    if app.config.get("DEBUG"):
        app.config["SWAGGER"] = {
            "title": "Quest - Question Engine API",
            "uiversion": 3,
            "specs_route": "/apidocs/",
            "securityDefinitions": {
                "Bearer": {
                    "type": "apiKey",
                    "name": "Authorization",
                    "in": "header",
                    "description": "Cognito JWT (admin) or player token. Format: Bearer <token>",
                }
            },
        }
        Swagger(app)

    # Register blueprints
    from src.routes.auth_routes import auth_bp
    from src.routes.audit_routes import audit_bp
    from src.routes.config_routes import config_bp
    from src.routes.event_routes import event_bp
    from src.routes.game_routes import game_bp
    from src.routes.question_bank_routes import bank_bp
    from src.routes.question_routes import question_bp
    from src.routes.leaderboard_routes import leaderboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(audit_bp)
    app.register_blueprint(config_bp)
    app.register_blueprint(event_bp)
    app.register_blueprint(game_bp)
    app.register_blueprint(bank_bp)
    app.register_blueprint(question_bp)
    app.register_blueprint(leaderboard_bp)

    # Create tables and seed config
    with app.app_context():
        db.create_all()
        _migrate_schema()
        _seed_config()
        _backfill_code_variants()

    return app


def _migrate_schema():
    """Apply additive, idempotent column migrations.

    db.create_all() creates missing tables but never alters existing ones, so
    new columns on already-created tables must be added explicitly. Each step
    checks the live schema first, making this safe to run on every boot.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    try:
        columns = {c["name"] for c in inspector.get_columns("code_variants")}
    except Exception:
        # Table not created yet (fresh DB) — create_all already handled it.
        return

    if "correct_answer" not in columns:
        db.session.execute(text("ALTER TABLE code_variants ADD COLUMN correct_answer TEXT"))
        db.session.commit()


def _seed_config():
    """Seed default global configuration if not present."""
    defaults = [
        (GlobalConfig.SHOW_CORRECT_ON_WRONG, "false", "Show the correct answer when a wrong answer is submitted"),
        (GlobalConfig.AUTO_PASS_ALL, "false", "Automatically pass all questions (dev/debug mode)"),
        (GlobalConfig.REQUIRE_BUILDER_ALIAS, "true", "Require a valid builder.aws.com alias as the player username"),
    ]
    for key, value, desc in defaults:
        if not GlobalConfig.query.filter_by(key=key).first():
            db.session.add(GlobalConfig(key=key, value=value, description=desc))
    db.session.commit()


def _backfill_code_variants():
    """Copy legacy per-question code_* fields into a CodeVariant row.

    Introduced alongside multi-language Coding questions so existing questions
    (which stored a single language plus one sample/hidden I/O pair directly on
    the Question) keep working. Idempotent: only creates a variant when one does
    not already exist for that question+language, so it is safe on every boot.
    """
    from src.models.models import Question, QuestionCategory, CodeVariant

    coding = Question.query.filter_by(category=QuestionCategory.Coding).all()
    created = 0
    for q in coding:
        language = (q.code_programming_language or "python").lower().strip()
        # Skip if a variant already exists for the legacy language, or if there
        # is no legacy code content worth preserving.
        if any(v.language == language for v in q.code_variants):
            continue
        if not any([
            q.code_sample_input,
            q.code_sample_output,
            q.code_hidden_input,
            q.code_hidden_output,
        ]):
            continue
        db.session.add(CodeVariant(
            question_id=q.id,
            language=language,
            starter_code=None,
            code_sample_input=q.code_sample_input,
            code_sample_output=q.code_sample_output,
            code_hidden_input=q.code_hidden_input,
            code_hidden_output=q.code_hidden_output,
        ))
        created += 1
    if created:
        db.session.commit()
