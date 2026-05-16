# Ghost Mesh Next Sprint Implementation Plan

## Status

Draft sprint plan for the first post-Phase 9 implementation cycle.

This plan assumes the current runtime has completed the open-source MVP through Phase 9: Patch Panel loading and validation, card runtime, worker leases, artifact references, node execution, shadow lanes, boundary adapters, observability, and public documentation. The next sprint should move Ghost Mesh from a technically complete runtime into a governed operating substrate where participants, permissions, workflow discovery, and intent-driven workflow genesis can be implemented without breaking the core choreography model.

## Sprint Theme

Implement the governance layer that lets Ghost Mesh answer four questions consistently:

- Who or what is taking this action?
- Which role and permission authorize it?
- Which workflow, bucket, node, card, artifact, or version is the action scoped to?
- Is the participant proposing, launching, or mutating work through the same governed mechanisms as every other participant?

## Source Inputs

This sprint plan synthesizes:

- Current Phase 0-9 implementation status in this repository.
- `ghost_mesh_participant_roles_and_authority_addendum_v_1.md`.
- The provided conversational workflow genesis use-case notes, interpreted as an external-client pattern rather than a runtime primitive.
- The architecture verification discussion that confirmed pipe-aware workers, artifact reference boundaries, shadow isolation, graph validation, junction routing, and idempotency are already in good shape.

## Non-Negotiable Principles

- Ghost Mesh is participant-neutral. Humans, agents, scripts, services, vendors, organizations, integrations, and subworkflows are participants.
- Participant type affects interface and authentication, not authority.
- Authority is explicit, scoped, versioned, and auditable.
- No participant receives implicit global authority.
- Workers remain pipe-aware and Patch Panels remain graph-aware.
- Routes remain dumb edges. Junctions and routing validators decide movement.
- No named assistant, agent framework, or conversational product is a runtime primitive. External clients are ordinary participants using uniform REST/MCP boundaries and scoped permissions.
- Patch Panels must remain explicit, versioned, portable, inspectable, and governable.
- Evidence remains append-only. Deletion is modeled primarily as state transition or redaction.

## Current Gap Analysis

The current codebase is structurally ready for this work, but it has deliberate MVP shortcuts:

- `worker_id`, `validator_id`, and `actor_id` are strings, not first-class participants.
- Authorization is mostly implicit in endpoint shape and runtime method choice.
- There is no durable role, permission, scope, policy, or participant assignment table.
- Patch Panel registration persists definitions, but does not expose registry metadata for discovery by intent, capability, risk, tool need, input/output type, owner, or tags.
- Proposed mutations exist, but their payloads are not yet constrained by a Patch Panel governance flow.
- Intent-driven genesis can be modeled cleanly with existing nodes and mutation primitives, but the project lacks the participant, registry, and proposal APIs needed to make it real without coupling to any one external client.

## Sprint Goals

1. Add a participant-neutral authority model with roles, permissions, scopes, and audit events.
2. Introduce authorization enforcement at key runtime and governance boundaries without overhauling all internal service methods at once.
3. Add Patch Panel registry metadata and discovery APIs.
4. Define the intent-driven workflow genesis path as a governed participant workflow.
5. Add a governed Patch Panel proposal lifecycle that can accept externally generated workflow proposals, validate them, review them, and promote them.
6. Preserve MVP ergonomics by providing development defaults and migration paths for existing string actor IDs.

## Out Of Scope

- Building a full user interface.
- Implementing production SSO, OAuth, SCIM, or enterprise identity federation.
- Building semantic search with embeddings as the first registry implementation.
- Giving any intent-ingress or workflow-architect participant unrestricted autonomous production publishing.
- Replacing existing worker SDK flows.
- Rewriting runtime internals around a large policy engine before a small explicit permission service exists.

## Proposed Phase Name

Phase 10: Participant Authority, Workflow Registry, and Intent-Driven Genesis.

## Workstream 1: Participant Authority Domain Model

### Implementation Tasks

- Add domain enums and models:
  - `ParticipantType`
  - `ParticipantStatus`
  - `RoleName` or role identifier value object
  - `PermissionName` or permission identifier value object
  - `ScopeType`
  - `Scope`
  - `Participant`
  - `Role`
  - `PermissionGrant`
  - `AuthorizationDecision`
  - `AuditAction`
- Keep participant type as metadata, not an authority class.
- Support direct permission grants and role-derived permission grants.
- Support scoped grants for organization, workflow, patch panel, bucket, node, card, artifact, version, and global development scope.
- Add soft lifecycle states: `active`, `suspended`, `archived`.
- Model role assignments with optional expiration to support temporary or delegated authority later.

### Suggested Minimal Permission Set

- `patch_panel:create`
- `patch_panel:edit_draft`
- `patch_panel:publish_version`
- `patch_panel:archive`
- `patch_panel:discover`
- `bucket:create`
- `node:create`
- `edge:create`
- `pipe_binding:create`
- `card:create`
- `card:claim`
- `card:submit_artifact`
- `card:release`
- `card:view`
- `validation:submit`
- `mutation:propose`
- `mutation:validate`
- `mutation:promote`
- `shadow:create`
- `shadow:complete`
- `sink:execute`
- `boundary:source_ingress`
- `boundary:sink_egress`
- `participant:manage`
- `permission:grant`
- `audit:view`

### Acceptance Criteria

- Participants can be represented as human, agent, script, service, vendor, organization, external integration, or subworkflow without changing authorization semantics.
- Roles and permissions are serializable with Pydantic.
- Scopes can represent global, workflow, patch panel, bucket, node, card, artifact, and version boundaries.
- Existing actor strings can be mapped to participant IDs without breaking existing API requests.

## Workstream 2: Persistence and Migration

### Implementation Tasks

- Add Alembic migration for:
  - `participants`
  - `roles`
  - `participant_roles`
  - `permission_grants`
  - `authorization_audit_events`
  - `patch_panel_registry_entries`
- Consider whether built-in roles should be stored in code, DB seed rows, or both. For the next sprint, code-defined built-ins plus DB assignments are likely enough.
- Add nullable `participant_id` columns only where needed for forward compatibility, while preserving existing `actor_id`, `worker_id`, and `validator_id` string columns until a later cleanup.
- Store authorization audit as append-only evidence separate from card event history, because not all authorization events target a card.

### Acceptance Criteria

- Fresh database migration succeeds from empty Postgres.
- Existing migrations still run in sequence.
- Existing tests pass without requiring real authentication.
- New participant fixtures can create role and permission state in both memory and Postgres-backed test paths.

## Workstream 3: Authorization Service

### Implementation Tasks

- Add `ghostmesh.auth` package with:
  - permission constants
  - scope matching utilities
  - `AuthorizationService`
  - in-memory repository
  - Postgres repository
  - FastAPI dependency helpers
- Implement `authorize(participant_id, permission, scope, context)` returning an explicit decision object.
- Record allow and deny decisions where useful, with reason, target scope, action, and request metadata.
- Add a development identity mode that accepts `X-Ghostmesh-Participant` and maps missing local participants to a configured development participant only when explicitly enabled.
- Keep bearer-token parsing minimal for now. The goal is an authority model, not production identity management.

### Initial Enforcement Points

- Register Patch Panel: `patch_panel:create` or `patch_panel:edit_draft`.
- Publish or promote mutation: `mutation:promote` and `patch_panel:publish_version`.
- Create Card: `card:create`.
- Claim Card: `card:claim`.
- Submit Artifact: `card:submit_artifact`.
- Human validator decision: `validation:submit`.
- Create shadow lane: `shadow:create`.
- Execute sink or boundary egress: `sink:execute` or `boundary:sink_egress`.
- Operator read endpoints: `audit:view` or a narrower observer permission.

### Acceptance Criteria

- Protected endpoints deny missing or unauthorized participants with consistent `403` responses.
- Existing tests can opt into a development bypass or seed an authorized participant.
- Authorization decisions are auditable.
- A participant with the same role but the wrong scope is denied.
- A non-human participant with the correct permission and scope is allowed.

## Workstream 4: Role Catalog and Governance Defaults

### Implementation Tasks

- Define built-in role templates:
  - Workflow Owner
  - Workflow Designer
  - Worker
  - Validator
  - Routing Validator / Junction Operator
  - Source Operator
  - Sink Operator
  - Reviewer / Approver
  - Shadow Participant
  - Learning / Optimizer
  - Observer
  - Admin
  - Intent Operator
  - Workflow Architect
- Keep templates inspectable and testable as data.
- Add seed helper for local development roles and sample participants.
- Ensure Admin is powerful but not magical. Admin must receive explicit grants.

### Acceptance Criteria

- Each built-in role maps to a concrete permission list.
- Intent Operator can admit structured intent into designated ingress scopes without receiving graph design authority by default.
- Workflow Architect has broad design and proposal permissions, but does not include direct production promotion by default.
- Shadow Participant cannot execute production sink permissions by default.
- Observer is read-only.

## Workstream 5: Patch Panel Registry

### Implementation Tasks

- Extend Patch Panel registration to accept registry metadata:
  - `name`
  - `description`
  - `tags`
  - `input_types`
  - `output_types`
  - `required_tools`
  - `required_permissions`
  - `risk_level`
  - `estimated_cost`
  - `estimated_latency`
  - `owner_participant_id`
  - `status`
- Add registry status values:
  - `draft`
  - `review`
  - `approved`
  - `published`
  - `archived`
  - `superseded`
- Add search/list APIs for exact metadata search first:
  - list by tag
  - list by input type
  - list by output type
  - list by required tool
  - list by risk level
  - list owned by participant
- Defer semantic/vector search until registry metadata is stable.

### Acceptance Criteria

- Authorized participants can discover candidate Patch Panels through a documented registry query API.
- Registry entries remain separate from runtime card state.
- Patch Panel definitions remain explicit graph documents.
- Archived and superseded workflows remain inspectable but are excluded from default launch search.

## Workstream 6: Governed Patch Panel Proposal Lifecycle

### Implementation Tasks

- Add a proposal model for new or modified Patch Panels:
  - `proposal_id`
  - `proposal_type`
  - `proposed_by`
  - `base_patch_panel_id`
  - `base_version`
  - `candidate_definition`
  - `registry_metadata`
  - `validation_report`
  - `status`
  - `review_events`
- Reuse existing `ProposedMutation` where possible, but add stronger typed payloads for Patch Panel proposals.
- On proposal creation:
  - validate Pydantic schema
  - run `PatchPanelValidator`
  - store validation report
  - emit audit event
- On approval:
  - require reviewer permission
  - register or publish the Patch Panel version
  - mark proposal approved/promoted
  - emit audit event
- On rejection:
  - require reviewer permission
  - store reason
  - keep proposal inspectable

### Acceptance Criteria

- Invalid externally generated Patch Panels fail before review.
- Valid generated Patch Panels can enter review without becoming production workflows.
- Approval is a separate permissioned action.
- Proposal history is append-only.

## Workstream 7: Intent-Driven Genesis MVP

### Implementation Tasks

- Add neutral Intent Operator and Workflow Architect participant fixtures and role templates.
- Add a generic genesis service boundary that performs deterministic workflow operations:
  - interpret an already-structured intent request
  - query registry candidates
  - create Cards for an existing Patch Panel when allowed
  - create Patch Panel proposals when no candidate matches
  - request governance approval
- Add `POST /genesis/intents` for standardized structured intent intake with desired inputs, outputs, constraints, and a mandatory deduplication key.
- Avoid free-form LLM integration in the first sprint. Accept structured intent input so the mesh mechanics can be proven independently of any agent framework.
- Add example Patch Panel for workflow genesis:
  - Source: structured user intent
  - Worker: generative designer seat
  - Validator: Patch Panel schema and topology validation
  - Reviewer: governance approval
  - Sink: registry publication
- Add docs/examples showing how any external conversational agent, automation tool, CLI, or webhook can call the generic genesis APIs later.

### Acceptance Criteria

- No agent-specific endpoint, role, table, or namespace is introduced.
- Intent ingress accepts structured requests through `/genesis/intents`.
- Any participant can discover existing Patch Panels if it has `patch_panel:discover`.
- Any participant can create Cards if it has `card:create` in scope.
- Any participant can propose Patch Panels if it has `mutation:propose` and design permissions.
- A proposing participant cannot publish its own proposal without reviewer/publisher permission.
- All genesis actions emit participant and authorization audit events.

## Workstream 8: API and SDK Updates

### Implementation Tasks

- Add participant management endpoints for local/dev use:
  - create participant
  - list participants
  - assign role
  - grant permission
  - inspect permissions
- Add registry endpoints:
  - create registry entry
  - update draft registry metadata
  - search registry
  - archive/supersede registry entry
- Add proposal endpoints:
  - create proposal
  - inspect proposal
  - approve proposal
  - reject proposal
- Update worker SDK to optionally send `X-Ghostmesh-Participant`.
- Preserve existing worker ID behavior for lease identity.

### Acceptance Criteria

- Existing worker integrations continue to function in development mode.
- New clients can use participant headers consistently.
- API docs describe participant identity separately from worker lease identity.

## Workstream 9: Tests and Verification

### Required Test Coverage

- Participant model serialization and validation.
- Scope matching rules.
- Role-derived permissions.
- Direct permission grants.
- Deny cases for wrong permission, wrong scope, suspended participant, and missing participant.
- Authorization audit append behavior.
- Protected endpoint allow/deny behavior.
- Patch Panel registry create/search/archive behavior.
- Patch Panel proposal validate/approve/reject behavior.
- Workflow Architect participants can discover and propose, but cannot self-promote.
- Shadow participant still cannot execute production sink.
- Existing Phase 0-9 regression suite passes.

### Verification Commands

```bash
poetry run ruff check .
poetry run pytest
poetry run alembic upgrade head
poetry run alembic current
docker compose config
```

## Suggested Sprint Sequence

### Day 1: Authority Skeleton

- Add domain models and permission constants.
- Add scope matcher.
- Add built-in role catalog.
- Add unit tests.

### Day 2: Persistence

- Add migrations and repository interfaces.
- Implement memory and Postgres-backed participant stores.
- Add migration and repository tests.

### Day 3: Authorization Enforcement

- Add FastAPI participant dependency.
- Protect the highest-risk endpoints first: Patch Panel registration, mutation promotion, shadow creation, sink execution, boundary egress.
- Add allow/deny endpoint tests.

### Day 4: Registry

- Add registry metadata model and table.
- Extend Patch Panel registration or add registry-specific endpoints.
- Add exact-match discovery APIs and tests.

### Day 5: Proposals and Intent-Driven Genesis MVP

- Add Patch Panel proposal lifecycle.
- Add Intent Operator and Workflow Architect roles plus the structured intent service.
- Add workflow genesis example and docs.

### Day 6: Hardening

- Run full verification.
- Update API docs and README links.
- Review audit event payloads for sensitive content leakage.
- Confirm artifact storage boundary remains intact.

## Decisions To Make Early

- Whether built-in role templates live only in code or are inserted as database rows.
- Whether registry metadata should be embedded in `PatchPanel.metadata` or stored in a separate first-class table. Recommended: separate table with a copy in metadata allowed for portability.
- Whether development mode should auto-create participants from headers. Recommended: no auto-create by default; provide a seed helper.
- Whether existing endpoints are all protected immediately or only high-risk endpoints are protected first. Recommended: protect high-risk and governance endpoints first, then expand in a follow-up sprint.

## Deliverables

- Participant and authority domain model.
- Role and permission catalog.
- Authorization service and audit trail.
- Participant persistence migration.
- Patch Panel registry metadata and discovery APIs.
- Governed Patch Panel proposal lifecycle.
- Intent-driven genesis MVP through neutral participants, roles, and `/genesis` APIs.
- Updated architecture and API documentation.
- Passing regression and new governance tests.

## Follow-Up Sprint Candidates

- Production authentication adapters.
- Semantic Patch Panel registry search.
- UI for governance approval queues.
- Redaction events and retention policy enforcement.
- Scoped secrets and tool access policies.
- Subworkflow execution.
- LLM-backed intent interpretation outside the runtime after the structured genesis mechanics are proven.
