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

Phase 2 runtime state:

- In-memory `CardRuntime` for card claim, submit, validate, move, and history
- Postgres-backed card runtime for durable card creation, movement, and evidence replay
- Runtime tables and Alembic migrations for workflow versions, buckets, cards, card locations, leases, artifacts, events, validation results, and idempotency records
- Basic lease and idempotency primitives
- REST endpoints for `/patchpanels`, `/cards`, claim, submit, validate, move, and history
- Minimal pipe-aware `WorkerClient`
- Shadow harness tests for linked, isolated shadow cards

Phase 3 card movement:

- Pipe-aware claim and submit flow backed by the runtime
- Postgres row-lock claim selection
- Lease renewal, release, and expiry recovery
- Idempotent claim, submit, renew, release, validate, and move operations
- REST endpoints for lease lifecycle actions
- Tests covering expired lease recovery, idempotent submit, and lease API behavior

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
