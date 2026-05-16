# Ghost Mesh

Ghost Mesh is a graph-native accountability substrate for human and AI work.

## Current Implementation Status

Phase 0 through Phase 9 are implemented.

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

- Pydantic domain models for Patch Panels, Cards, Buckets, Nodes, Edges, Pipe Bindings, Acceptance Contracts, Workflow Versions, Leases, Artifact References, and Events
- YAML/JSON Patch Panel loading
- NetworkX-backed graph validation
- Example Patch Panels
- Pytest coverage for core validation behavior

Phase 2 runtime state:

- In-memory `CardRuntime` for card claim, submit, validate, move, and history
- Postgres-backed card runtime for durable card creation, movement, and evidence replay
- Runtime tables and Alembic migrations for workflow versions, buckets, cards, card locations, leases, artifact references, events, validation results, and idempotency records
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

Phase 4 node execution:

- MVP `NodeExecutor` for Source, Worker, Human Validator, Junction, and Sink nodes
- Deterministic junction routing from validator evidence
- Sink execution evidence with optional external references
- Canonical Source to Worker to Human Validator to Junction to Sink workflow
- REST endpoints under `/nodes/.../execute`
- Tests covering accepted and rejected junction routes plus API node execution

Phase 5 worker and validator surfaces:

- Worker SDK helpers for claim, submit, renew, release, and assigned-card context
- SDK idempotency and optional bearer auth headers
- Worker context endpoint at `/workers/leases/{lease_id}/context`
- Human validator review queues at `/validators/{validator_id}/cards`
- Human validator card inspection at `/validators/cards/{card_id}`
- Human validator decision submission at `/validators/{validator_id}/cards/{card_id}/decision`
- Tests covering worker context, validator review/decision flow, and SDK headers

Phase 6 shadow and mutation safety:

- Shadow card links with production/shadow card references
- Sampling and maximum parallel shadow controls
- Shadow comparison metrics
- Production sink protection for shadow cards
- Proposed mutation records and mutation validation gates
- Promotion gate that only promotes validated mutations
- REST endpoints for `/shadows` and `/mutations`
- Tests proving shadow isolation, sampling/parallel limits, and mutation validation before promotion

Phase 6.5 artifact storage boundary:

- `ArtifactReference` replaces artifact content storage in the runtime contract
- `/cards/submit`, node worker execution, and the Worker SDK accept one or more artifact references
- Postgres stores only artifact reference metadata: `storage_ref`, `content_hash`, `content_type`, `size_bytes`, and metadata
- Event evidence records artifact IDs, hashes, and storage references, never artifact bodies
- Local filesystem/Git working-tree artifact store for development and version-controlled outputs
- S3/MinIO-compatible artifact store for production binaries and large media
- Acceptance contract rules can require artifact reference structure, count, and roles
- Migration `20260514_0004` removes the legacy artifact payload column and marks legacy rows for manual rehydration

Phase 7 boundary adapters:

- Controlled Source and Sink boundary contracts
- Webhook/API boundary endpoints at `/boundaries/source` and `/boundaries/sink`
- Source deduplication keys and Sink egress idempotency keys
- Payload and metadata mapping for external systems
- External reference recording for side effects
- GitHub issue intake and notification webhook example
- MCP documented as an edge integration mechanism, not the internal runtime

Phase 8 observability:

- Read-only operator endpoints under `/ops/...`
- Topology, Mermaid graph output, Cards by bucket, bucket load, active leases, worker activity, validator decisions, workflow versions, failed movements, metrics, and dashboard aggregate
- Structured lifecycle event logging

Phase 9 open-source readiness:

- Architecture, API, SDK, deployment, workflow, and AI adoption documentation
- Agent-facing skills in `docs/skills`
- Contributing guide, code of conduct, roadmap, and MIT license
- Docker image instructions and Helm chart stub
- CI validates Poetry install, Ruff, Alembic migrations, Docker Compose config, and tests

Docker Compose startup has been verified with the API and Postgres containers running locally.

## Documentation

- [Architecture](docs/architecture.md)
- [REST API](docs/api.md)
- [Worker SDK](docs/worker-sdk.md)
- [Deployment](docs/deployment.md)
- [Example workflows](docs/workflows.md)
- [Human to AI operating path](docs/ai-adoption-path.md)
- [Agent skills](docs/skills)

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

Human validator API sketch:

```bash
curl "http://localhost:8000/validators/human_validator/cards?patch_panel_id=hello_world"
curl "http://localhost:8000/validators/cards/<card_id>"
curl -X POST "http://localhost:8000/validators/human_validator/cards/<card_id>/decision" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: validator-decision-1" \
  -d '{"patch_panel_id":"hello_world","accepted":true,"score":9,"reason":"Approved"}'
```

Worker artifact submission sketch:

```python
from ghostmesh.artifacts import LocalGitArtifactStore
from ghostmesh.sdk import WorkerClient

client = WorkerClient("http://localhost:8000", worker_id="worker-1")
lease = client.claim(input_pipe="worker_input")
context = client.context(lease_id=lease["id"])
store = LocalGitArtifactStore("artifacts", repo_root=".")

artifact = client.upload_bytes(
    store,
    card_id=context["card"]["id"],
    data=b"draft output",
    filename="draft.txt",
    content_type="text/plain",
    metadata={"role": "draft"},
)
client.submit(
    lease_id=lease["id"],
    output_pipe="worker_output",
    artifact_refs=[artifact],
)
```
