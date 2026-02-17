# Quest - Question Engine

A backend Question Bank system providing REST APIs for quiz games with three question types: Multiple Choice, General Knowledge, and Coding.

## Quick Start (Local Development)

```bash
uv sync
uv run python run.py
```

Open http://127.0.0.1:5001 for the admin UI, or http://127.0.0.1:5001/apidocs/ for Swagger docs.

## Production

```bash
uv run gunicorn -c gunicorn.conf.py wsgi:app
```

## Environment Variables

Copy `.env.example` to `.env` and configure your settings. AWS credentials must be configured via AWS CLI profiles (`aws configure`) or IAM roles — never in .env files.
