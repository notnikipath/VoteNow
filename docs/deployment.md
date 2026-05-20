# Deployment

## Requirements

- Docker and Docker Compose
- Python 3.11 for local lint and tests

## Start

```bash
cd d:\Шарага\Кинжа13\Task_29_VoteNow
docker compose up --build -d
```

## Stop

```bash
docker compose down
```

## Validation

```bash
python -m ruff check .
python -m pytest -q
docker compose config
```

## Ports

- `8580` gateway
- `5178` frontend
- `8501-8506` services
- `55445` PostgreSQL
- `6393` Redis
