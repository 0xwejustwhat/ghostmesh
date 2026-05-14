# Ghost Mesh Phased Implementation Plan

## Status

Canonical implementation plan for the open-source Ghost Mesh MVP.

This document preserves the existing implementation blueprint as source material and refines the whitepaper and addenda into a phased execution roadmap. It assumes the repository currently starts from documentation and should grow into a Docker-deployable, auditable Ghost Mesh runtime.

## Current Implementation Status

Last updated: 2026-05-14

- Phase 0 and Phase 1 are implemented.
- The repository now includes a Poetry-managed Python package, FastAPI app, Docker Compose configuration, Alembic scaffolding, structured logging setup, Ruff linting, Makefile commands, and baseline GitHub Actions CI.
- Implemented Phase 1 scope includes Pydantic domain models, YAML/JSON Patch Panel loading, NetworkX-backed graph validation, example Patch Panels, and Pytest coverage.
- Verification commands: `poetry run ruff check .`, `poetry run pytest`, `poetry run alembic --help`, `docker compose config`, `docker compose up --build -d`, `curl http://localhost:8000/health`, and `docker compose exec -T postgres pg_isready -U ghostmesh -d ghostmesh`.
- Latest verification result: Ruff passed, 10 tests passed, Alembic CLI loaded, Docker Compose config validated, API and Postgres containers started, `/health` returned `{"status":"ok"}`, and Postgres accepted connections.

## Source Materials

This plan synthesizes the architecture and implementation decisions captured in:

- `ghost_mesh_updated_whitepaper v1.md`
- `ghost_mesh_implementation_addendum v1.md`
- `ghost_mesh_architecture_and_positioning_addendum v1.md`
- `ghost_mesh_nodes_addendum v1.md`
- `Ghost Mesh - Full Implementation Blueprint draft.md`

## Implementation North Star

Ghost Mesh is an accountability and workflow substrate for human and AI work. The implementation should stay graph-native, deterministic, explicit, and framework-agnostic.

Core principles:

- The Patch Panel defines the workflow graph.
- The runtime enforces graph movement.
- Cards carry payload, state, metadata, and append-only evidence.
- Workers are pipe-aware, not graph-aware.
- Validators enforce local acceptance contracts.
- Learning Nodes propose mutations but never mutate production directly.
- Shadow lanes prove worker and process changes before promotion.
- Source and Sink nodes are controlled boundary adapters.
- MCP is an edge integration mechanism, not the internal runtime.
- Agent frameworks may exist inside workers, but not inside the Ghost Layer.

## MVP Stack

- Language: Python
- Dependency management and packaging: Poetry
- API: FastAPI
- Schema validation: Pydantic v2 and JSON Schema
- Graph validation and analysis: NetworkX
- Runtime state: Postgres
- Migrations: Alembic
- Tests: Pytest
- Local deployment: Docker Compose
- API surface: REST first, MCP boundary adapters later
- Dashboard: React Flow later, with Mermaid acceptable for early topology visualization

## Phase 0: Repository and Development Foundation

Implementation status: complete and Docker Compose runtime verified.

### Goal

Create the runnable project foundation for contributors and future runtime work.

### Implementation

- Create a Poetry-managed Python project with `pyproject.toml`, package metadata, dependency groups, and documented lockfile workflow.
- Establish the initial package layout for API, domain schemas, runtime services, persistence, examples, and tests.
- Add Docker Compose with Postgres and the API service.
- Add Alembic scaffolding for database migrations.
- Add Pytest configuration and an initial smoke test.
- Add linting and formatting configuration.
- Add baseline CI that installs dependencies with Poetry and runs tests.
- Add basic structured logging configuration.
- Add developer commands for install, test, migration, and local startup through Poetry.

### Acceptance Criteria

- A contributor can install dependencies with Poetry.
- Tests can be run through a documented Poetry command.
- The API service can start locally through Docker Compose.
- Postgres is reachable from the application.
- CI runs the same install and test commands documented for local development.

## Phase 1: Core Domain Model and Patch Panel Validation

Implementation status: complete.

### Goal

Define the canonical data model and validate declarative Patch Panels before runtime execution exists.

### Implementation

- Implement Pydantic models for Cards, Buckets, Nodes, Edges, Pipe Bindings, Acceptance Contracts, Workflow Versions, Leases, Artifacts, and Events.
- Support the core node taxonomy: Source, Worker, Validator, Junction, Learning, Sink, and Subworkflow.
- Implement YAML and JSON Patch Panel loading.
- Validate Patch Panel schemas before graph analysis.
- Use NetworkX for reachability, invalid edge detection, dead-end detection, source/sink boundary checks, cycle analysis, and route analysis.
- Allow explicitly defined cycles, since Ghost Mesh is a workflow graph rather than a strict DAG.
- Validate that workers bind only to declared pipes and that pipes resolve to valid buckets.
- Add example Patch Panels, including a hello-world workflow and a cyclic review/rewrite workflow.

### Acceptance Criteria

- Valid Patch Panels load and produce versioned in-memory graph definitions.
- Invalid Patch Panels fail with actionable errors.
- Cyclic workflows are accepted when routes are explicit and bounded by declared rules.
- Dead-end, unreachable, and invalid edge cases are covered by tests.
- Pipe binding resolution is covered by tests.

## Phase 2: Runtime State, Cards, Buckets, and Evidence Trail

### Goal

Create durable card state and append-only evidence before implementing worker movement.

### Implementation

- Add Postgres tables for workflow versions, cards, card locations, buckets, artifacts, card events, idempotency records, leases, and validation results.
- Implement Alembic migrations for the initial schema.
- Implement repository or service-layer persistence for cards and events.
- Implement Source-node card creation with payload, metadata, workflow version, and initial bucket location.
- Implement append-only card event recording for all state changes.
- Implement card history replay from the event trail.
- Preserve the zero-loss visibility rule in the data model: a Card remains visible in its origin bucket until destination acceptance succeeds.

### Acceptance Criteria

- Cards can be created and persisted.
- A Card's current location can be queried.
- A Card's evidence trail can be replayed from events.
- Card creation emits an append-only event.
- Database tests prove events are not overwritten during normal operations.

## Phase 3: Claim, Lease, Submit, Validate, and Move

### Goal

Implement deterministic card movement with leases, idempotency, and zero-loss behavior.

### Implementation

- Implement pipe-aware claim flow for workers.
- Use Postgres row locking for initial claim concurrency control.
- Add lease acquisition, renewal, release, expiry, and recovery behavior.
- Compute lease duration from Card urgency, Node operational bounds, and runtime defaults.
- Implement artifact submission through worker output pipes.
- Implement idempotency records for internal transitions: claim once, submit once, validate once, move once.
- Implement destination acceptance before origin removal.
- Add failed drop-off handling that leaves the Card recoverable in the origin bucket.
- Add REST endpoints for card claim, lease renewal, artifact submission, validation, movement, and history.

### Acceptance Criteria

- Only one worker can hold an active lease for a Card at a time.
- Expired leases return Cards to claimable state.
- Duplicate claim, submit, validate, and move requests are handled idempotently.
- Failed movement does not make a Card disappear.
- End-to-end movement from Source to Worker to Validator to Sink works in tests.

## Phase 4: Node Execution MVP

### Goal

Execute the minimum useful Ghost Mesh workflow with Source, Worker, Validator, Junction, and Sink nodes.

### Implementation

- Implement MVP node behavior for Source, Worker, Validator, Junction, and Sink nodes.
- Model Learning and Subworkflow nodes in schemas, but defer full execution unless needed by the canonical workflow.
- Implement objective validators for schema, required fields, thresholds, and policy-style checks.
- Implement human-review validator flow with accept, reject, score, and reason fields.
- Implement deterministic junction routing based on validator result, score, metadata, or explicit rules.
- Implement Sink-node egress contract shape, including optional idempotency key definition and external reference recording.
- Add a canonical content workflow example using Source to Worker to Human Validator to Junction to Sink.

### Acceptance Criteria

- All seven node types can be declared in Patch Panel configuration.
- Source, Worker, Validator, Junction, and Sink can execute in the MVP runtime.
- Human validator decisions are recorded in the evidence trail.
- Junctions route deterministically from declared rules.
- The canonical content workflow runs end-to-end locally.

## Phase 5: Worker SDK and Human Validation Surface

### Goal

Make workers and human validators easy to integrate without exposing graph internals.

### Implementation

- Add a small Python worker SDK packaged through Poetry.
- Expose only pipe-aware worker operations: claim, renew lease, submit artifact, release, and inspect assigned Card context.
- Add SDK support for idempotency keys and lease-scoped authentication tokens when available.
- Add REST endpoints for human validators to list reviewable Cards, inspect payload and evidence, accept or reject artifacts, attach reasons, and submit scores.
- Add a minimal operator or validator surface if a UI is introduced in the MVP; otherwise provide a documented API workflow and examples.
- Ensure human and AI/script workers use the same Card, Lease, Artifact, Validation, and Event primitives.

### Acceptance Criteria

- A sample Python worker can claim a Card and submit an artifact through the SDK.
- A human validator can accept or reject an artifact through the API or minimal UI.
- Worker SDK operations do not require global workflow graph knowledge.
- All human and worker actions append evidence events.

## Phase 6: Shadow Lanes and Mutation Safety

### Goal

Enable safe worker and process auditions without allowing shadow activity to mutate production.

### Implementation

- Add shadow eligibility rules to Patch Panel configuration.
- Add shadow card links that connect production Cards to shadow Cards and shadow artifacts.
- Implement sampling controls and maximum parallel shadow limits.
- Ensure shadow workers and shadow Patch Panels cannot execute production Sinks.
- Implement Proposed Mutation Cards for prompts, workers, validators, routes, acceptance contracts, and workflow versions.
- Implement Mutation Validator and Promotion Gate concepts.
- Implement atomic Patch Panel version promotion after approved shadow results.
- Track comparison metrics for production versus shadow outputs, including acceptance rate, cost, latency, revision count, and validator scores.

### Acceptance Criteria

- Shadow Cards can be created and linked to production Cards.
- Shadow artifacts cannot mutate production state or trigger production egress.
- Sampling and maximum parallel limits are enforced.
- Proposed mutations require separate validation before promotion.
- Promotion updates the active Patch Panel version atomically.
- Tests prove worker and process shadow lanes remain isolated from production effects.

## Phase 7: Boundary Adapters and MCP Integration

### Goal

Connect Ghost Mesh to external systems through controlled Source and Sink boundaries.

### Implementation

- Implement Source-node boundary contracts for authorized ingress, payload mapping, target workflow version, and deduplication key.
- Implement Sink-node boundary contracts for authorized egress, payload mapping, idempotency key, and external reference recording.
- Add webhook Source and webhook Sink examples.
- Add MCP as an edge integration mechanism for Source and Sink nodes.
- Include one or two example adapters, such as GitHub issue intake and Slack notification or a generic HTTP webhook egress.
- Ensure external side effects are only guaranteed idempotent when mediated through Ghost-controlled Sink nodes or when the worker provides durable proof.

### Acceptance Criteria

- External systems can inject work through a controlled Source.
- Sinks record external references and egress idempotency keys.
- Duplicate Source events are deduplicated when a key is configured.
- Duplicate Sink execution is prevented when a matching egress idempotency record exists.
- Boundary adapter actions are included in the evidence trail.

## Phase 8: Observability, Dashboard, and Operational Readiness

### Goal

Make the mesh inspectable by operators and non-technical stakeholders.

### Implementation

- Add structured logs for claims, submissions, validations, movements, lease changes, failed drop-offs, shadow creation, and promotion.
- Add metrics for bucket load, lease age, worker activity, acceptance rate, retry rate, failed drop-offs, shadow comparisons, cost, and latency.
- Add OpenTelemetry tracing for card lifecycle transitions.
- Add read-only operational endpoints for topology, Card locations, bucket load, active leases, worker activity, validator decisions, workflow versions, and failed movements.
- Add an initial topology visualization using Mermaid or React Flow.
- Add dashboard views for live Patch Panel topology, Cards by bucket, lease status, evidence trail, and shadow performance.

### Acceptance Criteria

- Operators can inspect current workflow topology.
- Operators can find Cards by bucket and review their evidence trail.
- Lease and failed movement states are visible without database queries.
- Metrics and logs provide enough context to debug stuck Cards.
- Shadow comparison results are visible in operator views.

## Phase 9: Packaging, Documentation, and Open-Source Readiness

### Goal

Prepare the open-source core for contributors and enterprise evaluators.

### Implementation

- Add architecture documentation for Cards, Buckets, Patch Panels, Workers, Validators, Shadow Lanes, Source/Sink boundaries, and promotion.
- Add API documentation for REST endpoints.
- Add worker SDK documentation and examples.
- Add deployment documentation for Docker Compose and production-oriented configuration.
- Add example workflows, including the canonical content workflow and one boundary-adapter workflow.
- Add CONTRIBUTING, license, code of conduct, and roadmap documents.
- Add Docker image build instructions and optional Helm chart stub.
- Add CI checks for Poetry install, tests, migrations, and linting.
- Document the expected path from human production to AI shadow to supervised AI production to exception-based human oversight.

### Acceptance Criteria

- An unfamiliar developer can run the canonical workflow locally in under 15 minutes.
- The repository is public-ready.
- CI validates the documented contributor workflow.
- Documentation clearly distinguishes Ghost Mesh from agent orchestration frameworks.
- Documentation clearly states that Poetry is the dependency and packaging workflow.

## Test Strategy

- Unit tests for Pydantic schemas, Patch Panel parsing, pipe binding resolution, route validation, acceptance contract evaluation, and idempotency keys.
- Graph validation tests for allowed cycles, unreachable nodes, dead ends, invalid shadow routes, invalid source/sink boundaries, invalid edge conditions, and missing pipe bindings.
- Database tests for migrations, row-locking claim contention, lease expiry, duplicate submissions, append-only event guarantees, and idempotency records.
- Integration tests for card creation, claim, lease renewal, artifact submission, validation, movement, event replay, failed drop-off recovery, and validator routing.
- End-to-end tests for the canonical content workflow and at least one boundary-adapter workflow.
- Shadow tests proving that shadow artifacts cannot mutate production state and that promotion updates the active Patch Panel version atomically.
- SDK tests proving workers can operate through pipes without graph awareness.
- Observability tests confirming key logs, metrics, and traces are emitted for lifecycle transitions.

## Explicit Non-Goals for the MVP

- Do not build a hosted enterprise control plane in the open-source MVP.
- Do not use LangGraph or any agent runtime as the Ghost Layer runtime.
- Do not make MCP the internal workflow engine.
- Do not allow Learning Nodes to mutate production directly.
- Do not make workers responsible for global routing.
- Do not require AI validators to have production authority before shadow evaluation.
- Do not use Git as the live runtime queue.

## Assumptions

- The existing draft blueprint remains preserved as source material.
- This document is the canonical execution plan unless superseded by a later canonical plan.
- Poetry is the default dependency management and package workflow for the Python implementation.
- The first implementation target is an open-source MVP core.
- Enterprise hosted features, advanced settlement systems, and marketplace capabilities are future layers.
- Human-first validation is the safest initial path.
- AI evaluators and advanced Learning Nodes should begin in shadow before receiving production authority.
- Source and Sink idempotency is guaranteed only for Ghost-controlled boundaries or when durable external proof is recorded.
