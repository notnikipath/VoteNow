# VoteNow

VoteNow is a microservice platform for online surveys and voting with respondent verification, anti-fraud checks, real-time analytics, and report export.

## Modules

- `api-gateway` - orchestration, auth token, public dashboard API
- `survey-service` - survey builder, question types, visibility, schedule
- `response-service` - response validation and storage
- `verification-service` - invited-list voting, SMS or email confirmation, duplicate control
- `analytics-service` - live metrics, charts, tables, forecasting, throughput checks
- `export-service` - async Excel or PDF report generation with Celery
- `notification-service` - outbound notifications
- `frontend` - public vote form and live dashboard UI

## Mandatory coverage

- Supported question types: single choice, multiple choice, rating, open text, tournament voting
- Public link and embeddable widget snippet
- Captcha and per-IP rate limiting
- Invited-only voting and SMS or email verification
- Charts and tables in analytics
- Excel and PDF export
- Public real-time dashboard

## Optional improvements implemented

- Survey length recommendation
- Sentiment analysis for open text answers
- Forecasted turnout
- Adaptive question branching via `next_map`
- Live result caching
- Parallel write planning
- Asynchronous report generation with Celery

## Stack

- Backend: FastAPI
- Storage: PostgreSQL, Redis
- Queue: Celery
- Frontend: React + Vite

## Local run

```bash
cd 'your/project/folder'
docker compose up --build -d
```

## URLs

- Frontend: `http://localhost:32089`
- Gateway docs: `http://localhost:32082/docs`
- Gateway health: `http://localhost:32082/health`
- Services health: `http://localhost:32082/services/health`

## Validate

```bash
python -m ruff check .
python -m pytest -q
docker compose config
```

## Demo workflow

```bash
python scripts/demo_pipeline.py
```
