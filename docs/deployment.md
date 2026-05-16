# Deployment

## Local Development

```bash
poetry install
poetry run ruff check .
poetry run pytest
poetry run uvicorn ghostmesh.api.main:app --reload
```

Poetry is the dependency and packaging workflow for this repository.

## Docker Compose

```bash
docker compose config
docker compose up --build -d
curl http://localhost:8000/health
curl http://localhost:8000/cards
docker compose exec -T postgres pg_isready -U ghostmesh -d ghostmesh
```

The Compose stack starts Postgres, runs Alembic migrations, and serves the FastAPI app with the Postgres runtime backend.

## Docker Image

```bash
docker build -t ghostmesh:local .
docker run --rm -p 8000:8000 \
  -e GHOSTMESH_RUNTIME_BACKEND=memory \
  ghostmesh:local
```

For production-like runs, set:

- `DATABASE_URL`
- `GHOSTMESH_RUNTIME_BACKEND=postgres`
- `GHOSTMESH_ENVIRONMENT`
- `LOG_LEVEL`

## Migrations

```bash
poetry run alembic upgrade head
poetry run alembic current
```

Migrations expect a reachable Postgres database when run online.

## Kubernetes

An initial Helm chart stub lives in `deploy/helm/ghostmesh`. It is intentionally small and should be hardened before production use.
