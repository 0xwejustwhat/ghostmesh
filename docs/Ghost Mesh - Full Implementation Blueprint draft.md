**Ghost Mesh - Full Implementation Blueprint v1.0**

**Status:** Ready for execution **Scope:** MVP Core (Phase 0-5) → Production-grade open-source foundation **Target Timeline:** 12 weeks (aggressive but achievable with focused effort) **Success Metric:** A self-contained, auditable, Docker-deployable Ghost Mesh runtime that can run the canonical content workflow end-to-end with shadow auditions and safe mutations.

**Phase 0: Foundations & Dev Environment (Week 1)**

**Goal:** Running skeleton with validated Patch Panel and basic persistence.

**Deliverables**

- Full project skeleton (Poetry, Docker, Alembic, pre-commit, just/Makefile)
- Complete Pydantic v2 model library (Card, Lease, PatchPanel, NodeDefinition, AcceptanceContract, ShadowLink, etc.)
- Postgres schema + first migration
- PatchPanelValidator (NetworkX: cycle detection, reachability, dead-ends, shadow rules)
- Minimal FastAPI app (/health, /v1/patchpanels, basic card CRUD)
- examples/hello-world-patchpanel.yaml + loader
- First integration test suite (pytest)
- Observability scaffolding (structured logging + OTEL hooks)
- Local keystore stub (age-encrypted SQLite)

**Key User Stories**

- As a developer, I can docker compose up and have a working Ghost Mesh in < 5 minutes.
- As a workflow author, I can load a YAML Patch Panel and have it validated.
- As an operator, I can see structured logs for every operation.

**Acceptance Criteria**

- All tests green
- NetworkX validates a cyclic graph correctly
- Card can be created and persisted

**Phase 1: Core Runtime & Card Lifecycle (Weeks 2-3)**

**Goal:** Deterministic card movement with leases and auditability.

**Deliverables**

- CardMovementEngine + idempotency middleware
- Lease management (claim, release, expiry, row-level locking)
- Append-only card_events audit log
- Basic Worker SDK (Python) - pipe-aware claim/submit
- REST endpoints: /cards/{id}/claim, /cards/{id}/submit, /cards/{id}/move
- GitOps loader for Patch Panel (versioned)
- Idempotency enforcement (24h window)

**Key User Stories**

- As a Worker (human or AI), I can claim a Card via input pipe and submit artifact via output pipe.
- As the runtime, I enforce exactly-once movement and full audit trail.
- As an operator, I can replay any Card's history from the evidence trail.

**Acceptance Criteria**

- End-to-end: Source → Worker → Validator → Sink works with zero data loss on failure
- Lease expiry automatically returns Card to bucket
- 100% of state changes are auditable

**Phase 2: Full Node Taxonomy & Validation (Weeks 4-6)**

**Goal:** Core node taxonomy + Acceptance Contracts.

**Deliverables**

- Abstract BaseNode + concrete implementations (Source, Worker, Validator, Learning, Sink, Subworkflow)
- AcceptanceContract engine (Pydantic + custom rules + human hook)
- Routing validator logic (rule-based + score-based)
- Subworkflow support (recursive Patch Panel execution)
- Human validator UI stub (simple React Flow + form)
- Node-specific redaction hooks

**Key User Stories**

- As a Validator (human), I can review a Card and accept/reject with reason.
- As a routing Validator, I can route based on score or metadata.
- As a workflow designer, I can nest subworkflows.

**Acceptance Criteria**

- Core node types can be declared in YAML and executed
- Acceptance Contracts are enforceable and versioned
- Human + AI worker symmetry is complete

**Phase 3: Shadow Patch Panels & Mutation Safety (Weeks 7-8)**

**Goal:** Safe auditions and evidence-driven evolution.

**Deliverables**

- Shadow Card creation + linkage (shadow_card_links table)
- Parallel Shadow Patch Panel execution (sampling + max_parallel enforcement)
- Proposed Mutation Card flow
- Mutation Validator + Promotion Gate
- Shadow vs Production comparison metrics
- Safe Patch Panel hot-swap (v1 → v2)

**Key User Stories**

- As a Learning Node, I can propose a mutation that goes through shadow audition.
- As an operator, I can promote a winning shadow worker/workflow.
- As a security officer, I know shadow workers never affect production.

**Acceptance Criteria**

- Shadow sampling works correctly
- Promotion updates Patch Panel version atomically
- Subworkflow shadowing is recursive and correct

**Phase 4: Boundaries, MCP & Observability (Weeks 9-10)**

**Goal:** Real-world integration and production readiness.

**Deliverables**

- FastMCP Source/Sink adapters (GitHub, Slack, etc. examples)
- Full observability (Prometheus metrics + Grafana dashboard stub)
- OpenTelemetry tracing on every transition
- Worker authentication & lease-scoped secret tokens
- Basic admin dashboard (React Flow visualization of live Patch Panel + cards)

**Key User Stories**

- As an external system, I can inject work via MCP Source.
- As an operator, I can see live topology, bucket load, and shadow performance.
- As a worker developer, I can get scoped credentials for my lease.

**Acceptance Criteria**

- End-to-end content workflow (from whitepaper) runs with real MCP boundaries
- All key metrics are emitted

**Phase 5: Polish, Packaging & Open Source (Weeks 11-12)**

**Goal:** Ship the open-core foundation.

**Deliverables**

- Complete documentation (architecture, API, deployment, worker SDK)
- CI/CD (GitHub Actions)
- Packaging (Docker images, Helm chart stub)
- Example workflows (content production + one more)
- License (MIT), CONTRIBUTING.md, code of conduct
- Initial public roadmap

**Key User Stories**

- As an open-source contributor, I can easily run, test, and extend Ghost Mesh.
- As an enterprise evaluator, I can deploy the core in my environment and integrate workers.

**Acceptance Criteria**

- Repo is public-ready
- Someone unfamiliar with the project can run the full content workflow in < 15 minutes

**Overall Project Risks & Dependencies**

- **Primary Risk:** Shadow cardinality → mitigated by explicit sampling + limits
- **Primary Dependency:** Postgres row locking behavior under load → will validate in Phase 1
- **Nice-to-have (post-MVP):** Full React dashboard, advanced Learning Node examples, marketplace scaffolding

**Recommendation on PRD vs This Blueprint**

**This Implementation Blueprint is sufficient** for the next 3-4 months of development. It contains:

- All architectural decisions
- Phased deliverables with acceptance criteria
- User stories at the right granularity
- Technical constraints and performance budgets

We can treat this document as the **living PRD**. I can expand any phase into more detailed user stories or acceptance criteria on demand.
