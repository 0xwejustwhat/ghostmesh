# Ghost Mesh

Ghost Mesh is a graph-native accountability substrate for human and AI work.

## Current Implementation Status

Phase 0 and Phase 1 are implemented.

Phase 0 foundation:

- Poetry-managed Python package
- FastAPI app with health endpoint
- Docker Compose configuration for API and Postgres
- Alembic migration scaffolding
- Structured logging setup
- Ruff linting and formatting configuration
- Makefile developer commands
- Baseline GitHub Actions CI

Phase 1 graph model and validation:

- Pydantic domain models for Patch Panels, Cards, Buckets, Nodes, Edges, Pipe Bindings, Acceptance Contracts, Workflow Versions, Leases, Artifacts, and Events
- YAML/JSON Patch Panel loading
- NetworkX-backed graph validation
- Example Patch Panels
- Pytest coverage for core validation behavior

Docker Compose startup has been verified with the API and Postgres containers running locally.

## Developer Setup

```bash
poetry install
poetry run ruff check .
poetry run pytest
```

Run the local API without Docker:

```bash
poetry run uvicorn ghostmesh.api.main:app --reload
```

Run the local stack with Docker:

```bash
docker compose up --build -d
curl http://localhost:8000/health
```
