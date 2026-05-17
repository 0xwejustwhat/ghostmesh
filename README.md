# Ghost Mesh

Ghost Mesh is a headless, decentralized choreography layer for outcome-oriented agentic workflows and automated production pipelines. It is a substrate designed to transform non-deterministic intelligence into predictable, human-in-the-loop verified business infrastructure.

At the capability layer, Ghost Mesh is participant-neutral. Humans, AI models, terminal scripts, services, integrations, and automated systems are all governed by authenticated `Participant` records, granular `PermissionName` strings, and cryptographic `Scope` constraints. Interface type never grants authority by itself.

## The Core Problem & Philosophy

Traditional workflow platforms rely on a central orchestrator that holds master graph state and pushes updates to passive agents. This model breaks down at scale because it creates execution bottlenecks, tightly coupled integration surfaces, a lack of structured auditability across human-AI boundaries, and weak protection for production state from raw LLM hallucinations.

Ghost Mesh takes the opposite posture:

```text
Do not orchestrate agents. Choreograph work.
```

The platform isolates execution down to localized, stateless, pipe-aware stations. Data flows autonomously through immutable tracking containers called Cards, guided entirely by static network patch panels. A worker leases from an input pipe, emits structured artifacts, and releases the Card. It does not need global graph authority, hidden routing knowledge, or privileged access to production side effects.

## System Primitives & Architectural Taxonomy

A Patch Panel is the immutable topology that defines how Cards move. Six primary node categories handle all data movement inside that topology:

- **Source Nodes**: Ingress gateways that admit work packages into the mesh by translating external events, webhooks, API triggers, and conversational intents into standard Cards.
- **Worker Nodes**: Narrow, decentralized labor stations that lease a Card from an input pipe, perform a specific task, submit structured file artifacts, and release their lease.
- **Validator Nodes**: Verification checkpoints that evaluate a Card's current state against an explicit acceptance contract. This includes standard binary checkers for accept/reject outcomes and Routing Validators (Junctions) that natively choose one of several authorized exit pipes to direct the Card downstream. A routing junction is not a standalone node class or type; it is a multi-cardinality subtype of a standard Validator Node whose declared `output_pipes` and acceptance contract govern the only permitted exits.
- **Learning Nodes**: Non-blocking optimization layers that observe historical performance logs to propose process adaptations.
- **Sink Nodes**: Egress gates authorized to map completed Card data out to external production networks.
- **Subworkflow Nodes**: Nested sub-graphs indexed in the registry by their input/output boundary signatures.

Authority remains separate from node shape. Any participant operating any node must pass the same permission and scope checks before claiming Cards, submitting artifacts, validating outcomes, promoting mutations, or executing sinks.

## Intent-Driven Genesis

New automated tracks are spun up on demand through explicit intent creation rather than chat-session control transfer.

External conversational clients may let users express high-level requirements in natural language. These clients can operate through MCP, REST, CLI wrappers, webhooks, or other integration surfaces, but they remain decoupled external controllers. They manage conversational sandboxes only until a bounded intent is explicitly submitted.

Once an intent is pushed through `/genesis/intents`, control is surrendered to the immutable topology of the target Patch Panel graph. The runtime evaluates the request against the Patch Panel Registry using dual identifiers: `patch_panel_id` and `version`. If a compatible published graph exists, Ghost Mesh creates a Card in the authorized ingress scope and the Patch Panel governs all subsequent movement.

If a gap is detected, an agent or other participant filling the Workflow Architect role may draft a proposed topology modification layout. Genesis submits that proposal as a normal Card in the system `system_pp_approval` Patch Panel. The proposal remains quarantined by declared buckets and validator exits until independent validation and governance route it to either rejection or the registry publication sink. The proposing participant cannot publish its own topology, bypass validators, or execute production sinks unless separately granted those permissions in the relevant scope.

## Technical Quickstart

Prerequisites:

- Python 3.11+
- Docker
- Poetry

Install dependencies:

```bash
poetry install
```

Boot the local environment and database:

```bash
docker compose up -d
poetry run alembic upgrade head
```

Run the suite:

```bash
poetry run ruff check .
poetry run pytest
```

Run the API locally:

```bash
poetry run uvicorn ghostmesh.api.main:app --reload
```

## Comprehensive Documentation Index

- [Core Whitepaper](docs/ghost_mesh_updated_whitepaper%20v1.md) - The foundational technical thesis on labor liquidity substrates.
- [System Architecture](docs/architecture/core_runtime.md) - State isolation layers, postgres index layouts, and artifact boundaries.
- [Identity & RBAC Engine](docs/architecture/participant_authority.md) - Comprehensive permission grids, scopes, and functional role catalogs.
- [Patch Panel Registry](docs/architecture/patch_panel_registry.md) - Contract tracking, version control, and multi-version pipeline index maps.
- [Intent-Driven Genesis](docs/architecture/intent_driven_genesis.md) - Structured intent, proposal Cards, and `system_pp_approval` governance.
- [Skill Catalogs](docs/skills/README.md) - MCP configuration models and prompt engineering rules for independent worker roles.
