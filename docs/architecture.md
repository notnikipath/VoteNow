# Architecture

## Context

VoteNow provides a full voting lifecycle: survey design, public distribution, anti-fraud response collection, respondent verification, real-time analytics, and async report exports.

## Service map

- `api-gateway`: auth token, workflow orchestration, public dashboard aggregation
- `survey-service`: survey schema and schedule management
- `response-service`: answer validation and response persistence
- `verification-service`: invited lists, SMS or email code confirmation, duplicate protection
- `analytics-service`: live metrics, chart and table generation, forecasting
- `export-service`: asynchronous Excel and PDF generation through Celery
- `notification-service`: outbound email, SMS, and webhook notifications

## Infrastructure

- PostgreSQL: operational storage baseline
- Redis: rate limiting state, cache, and Celery broker or backend
- Celery worker: asynchronous export jobs
- Docker Compose: local multi-service deployment

## Main workflow

1. Load survey by public token
2. Validate captcha and per-IP throttle
3. Validate invited list and verification code if required
4. Check duplicate fingerprint
5. Save response
6. Update live analytics
7. Optionally trigger export tasks

## Quality targets

- Survey load target: under 2 seconds
- Throughput target: up to 10,000 responses per minute
- Scale target: 1 million respondents via horizontal service scaling and partitioning strategy
