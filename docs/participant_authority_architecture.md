# Participant Authority Architecture

## Purpose

This document defines the next Ghost Mesh authority layer: participant-neutral identity, role-based capability grants, scoped permissions, and auditable authorization decisions.

The core design point is simple:

```text
Participant type affects interface.
Permissions affect authority.
```

Humans, AI agents, scripts, vendors, organizations, integrations, services, and subworkflows are all participants. None receive implicit authority because of what they are.

## Design Goals

- Represent all actors as participants.
- Keep authority explicit and scoped.
- Avoid magical root users and hidden bypasses.
- Make every sensitive decision auditable.
- Preserve current worker, validator, source, sink, shadow, and mutation primitives.
- Add authorization incrementally without rewriting the runtime in one pass.

## Core Concepts

### Participant

A participant is any entity that can attempt an action.

Suggested shape:

```yaml
participant:
  id: participant_id
  type: human | agent | script | vendor | organization | system_service | external_integration | subworkflow
  display_name: optional
  status: active | suspended | archived
  trust_level: optional
  auth_method: optional
  metadata: {}
```

### Role

A role describes intended responsibility and carries a reusable permission set.

Examples:

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
- Hermes Chief of Staff

### Permission

A permission describes a concrete action, such as:

```text
card:claim
card:submit_artifact
validation:submit
mutation:promote
sink:execute
```

### Scope

A scope constrains where a permission applies.

Suggested scope types:

- `global`
- `organization`
- `workflow`
- `patch_panel`
- `workflow_version`
- `bucket`
- `node`
- `card`
- `artifact`

### Authorization Decision

An authorization decision records the result of checking participant, permission, scope, object state, and policy context.

Suggested shape:

```yaml
authorization_decision:
  id: decision_id
  participant_id: participant_id
  permission: card:claim
  scope:
    type: bucket
    id: draft_bucket
  allowed: true
  reason: matched role Worker in workflow scope
  evaluated_at: timestamp
  metadata: {}
```

## Data Model

### `participants`

- `id`
- `type`
- `display_name`
- `status`
- `trust_level`
- `auth_method`
- `participant_metadata`
- `created_at`
- `archived_at`

### `roles`

- `id`
- `name`
- `description`
- `role_metadata`
- `created_at`

### `participant_roles`

- `id`
- `participant_id`
- `role_id`
- `scope_type`
- `scope_id`
- `assigned_by`
- `expires_at`
- `created_at`
- `revoked_at`

### `permission_grants`

- `id`
- `participant_id`
- `role_id`
- `permission`
- `scope_type`
- `scope_id`
- `granted_by`
- `expires_at`
- `created_at`
- `revoked_at`

One row may target either a participant or a role. Role grants make built-in roles easy to inspect, while direct participant grants support exceptions.

### `authorization_audit_events`

- `id`
- `participant_id`
- `permission`
- `scope_type`
- `scope_id`
- `allowed`
- `reason`
- `request_ref`
- `target_ref`
- `event_metadata`
- `created_at`

## Scope Matching

The minimum viable matcher should support:

- Exact scope match.
- Global scope match.
- Workflow parent scope matching child workflow objects when the object can be resolved to that workflow.
- Patch Panel scope matching versions of that Patch Panel.

The first implementation should keep scope inheritance conservative. When in doubt, deny and make the caller request a more exact grant.

## Built-In Role Defaults

### Workflow Owner

Typical grants:

- `patch_panel:create`
- `patch_panel:edit_draft`
- `patch_panel:publish_version`
- `patch_panel:archive`
- `bucket:create`
- `node:create`
- `edge:create`
- `pipe_binding:create`
- `mutation:validate`
- `mutation:promote`
- `shadow:create`
- `permission:grant` within owned workflow scope

### Workflow Designer

Typical grants:

- `patch_panel:create`
- `patch_panel:edit_draft`
- `bucket:create`
- `node:create`
- `edge:create`
- `pipe_binding:create`
- `mutation:propose`

No production publishing by default.

### Worker

Typical grants:

- `card:view`
- `card:claim`
- `card:submit_artifact`
- `card:release`

Workers remain pipe-aware and do not receive routing, mutation, or sink authority by default.

### Validator

Typical grants:

- `card:view`
- `validation:submit`

### Sink Operator

Typical grants:

- `sink:execute`
- `boundary:sink_egress`

### Shadow Participant

Typical grants:

- `card:view`
- `card:claim`
- `card:submit_artifact`
- `shadow:complete`
- `mutation:propose`

No production sink authority by default.

### Observer

Typical grants:

- `card:view`
- `patch_panel:discover`
- `audit:view`

Read-only unless separately granted more authority.

### Hermes Chief of Staff

Typical grants:

- `patch_panel:discover`
- `patch_panel:create`
- `patch_panel:edit_draft`
- `bucket:create`
- `node:create`
- `edge:create`
- `pipe_binding:create`
- `card:create`
- `mutation:propose`
- `shadow:create`

Hermes should not receive `mutation:promote` or `patch_panel:publish_version` by default.

## Enforcement Boundaries

The first sprint should protect high-risk and governance-heavy operations:

- Patch Panel registration and publishing.
- Card creation.
- Card claim and submit.
- Validator decisions.
- Shadow lane creation.
- Mutation validation and promotion.
- Sink execution.
- Boundary source ingress and sink egress.
- Operator/audit reads.

Internal runtime helpers can continue accepting actor strings, but API and service boundaries should resolve those strings to participants before authorizing sensitive actions.

## Development Mode

Development mode should make local testing easy without hiding the architecture:

- Accept `X-Ghostmesh-Participant`.
- Provide seeded sample participants and roles.
- Allow explicit test bypass only in test settings.
- Do not silently grant global authority to every caller.

## Audit Semantics

Authorization audit events should be append-only. Denials are important evidence and should be retained for governance and debugging.

Audit payloads should avoid storing raw artifact bodies or sensitive external payloads. Store references, target IDs, permission names, scopes, and concise reasons.

## Deletion Semantics

Participants, role assignments, and permission grants should be revoked, suspended, archived, or expired rather than physically deleted once used in execution evidence.

Recommended lifecycle transitions:

- participant: `active -> suspended -> archived`
- role assignment: active row with `revoked_at`
- permission grant: active row with `revoked_at`

## Implementation Notes

- Keep permission constants in code so tests and API handlers do not depend on raw strings scattered across the codebase.
- Add role templates as data, not branching logic.
- Use Pydantic for request/response models and SQLAlchemy tables for persistence.
- Keep the policy engine intentionally small in the first sprint.
- Prefer deny-by-default when participant, permission, or scope cannot be resolved.
