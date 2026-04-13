import os
from datetime import timedelta


class Config:
    """Base configuration."""
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Cognito settings for admin authentication
    COGNITO_REGION = os.environ.get("COGNITO_REGION", "eu-central-1")
    COGNITO_USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
    COGNITO_APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")

    # Player token secret — used only for game-play API tokens (not admin)
    PLAYER_TOKEN_SECRET = os.environ.get("PLAYER_TOKEN_SECRET", "")

    # Strands / Bedrock — credentials via AWS CLI profiles or IAM roles, never .env
    AWS_REGION = os.environ.get("AWS_REGION", "eu-west-1")
    BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "eu.anthropic.claude-sonnet-4-20250514-v1:0")


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///quest_dev.db")
    # In development, allow a fallback player token secret
    PLAYER_TOKEN_SECRET = os.environ.get("PLAYER_TOKEN_SECRET", "dev-player-secret-change-in-production")


class ProductionConfig(Config):
    DEBUG = False
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///quest.db")


config_by_name = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
