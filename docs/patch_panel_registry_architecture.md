# Patch Panel Registry Architecture

## Purpose

The Patch Panel registry makes explicit workflow definitions discoverable, governable, and reusable. It is the missing bridge between the current runtime, which can register and execute Patch Panels, and intent-driven workflow genesis, which needs to find or propose workflows from user intent.

The registry does not replace Patch Panels. Patch Panels remain declarative graph documents. The registry indexes them.

## Design Goals

- Preserve Patch Panels as explicit, portable workflow definitions.
- Add metadata that supports discovery by humans, agents, scripts, webhooks, and other external clients.
- Keep runtime state separate from workflow definition state.
- Support draft, review, published, archived, and superseded lifecycle states.
- Make workflow discovery permissioned and auditable.
- Start with exact metadata search before semantic search.

## Registry Entry Shape

Suggested model:

```yaml
patch_panel_registry_entry:
  id: registry_entry_id
  patch_panel_id: content_campaign
  version: 1.0.0
  name: Content Campaign
  description: Draft, validate, approve, and publish campaign assets.
  tags:
    - content
    - marketing
  input_types:
    - campaign_brief
  output_types:
    - approved_campaign_assets
  required_tools:
    - artifact_store
    - human_review
  required_permissions:
    - card:create
    - card:claim
    - validation:submit
  risk_level: medium
  estimated_cost: low
  estimated_latency: hours
  owner_participant_id: participant_id
  status: draft | review | approved | published | archived | superseded
  supersedes_entry_id: optional
  metadata: {}
```

## Lifecycle

### Draft

Workflow metadata and graph definition can be edited by participants with draft edit permission.

### Review

The Patch Panel proposal has passed schema and graph validation and is waiting for governance review.

### Approved

The proposal has been accepted by a reviewer but may not yet be active for production launches.

### Published

The workflow version is available for normal discovery and launch.

### Archived

The workflow should not be launched by default, but remains inspectable.

### Superseded

The workflow has been replaced by a newer entry. It remains inspectable for evidence replay and historical audit.

## Persistence

Suggested table: `patch_panel_registry_entries`.

Columns:

- `id`
- `patch_panel_id`
- `version`
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
- `supersedes_entry_id`
- `registry_metadata`
- `created_at`
- `updated_at`
- `archived_at`

Store list fields as JSON for the MVP. Add indexes later after real query patterns are proven.

## Search API

Start with exact metadata filters:

```text
GET /registry/patchpanels
GET /registry/patchpanels?tag=outreach
GET /registry/patchpanels?input_type=campaign_brief
GET /registry/patchpanels?output_type=approved_assets
GET /registry/patchpanels?required_tool=github
GET /registry/patchpanels?risk_level=low
GET /registry/patchpanels?owner_participant_id=...
```

Default search should exclude archived and superseded entries unless requested.

## Governance API

Suggested endpoints:

```text
POST /registry/patchpanels
PATCH /registry/patchpanels/{entry_id}
POST /registry/patchpanels/{entry_id}/archive
POST /registry/patchpanels/{entry_id}/supersede
GET /registry/patchpanels/{entry_id}
```

Registry mutation should require scoped Patch Panel or workflow owner/designer authority.

## Intent-Driven Discovery Flow

Authorized intent-ingress and workflow-architect participants should discover workflows in this order:

1. Parse structured intent into candidate metadata filters.
2. Search published registry entries.
3. Rank exact matches locally using tags, input types, output types, risk, cost, and required tools.
4. If a suitable workflow exists, create Cards under permissioned scope.
5. If no suitable workflow exists, create a Patch Panel proposal.

Semantic search can be added later as a ranking layer, not as the source of truth.

## Relationship To `PatchPanel.metadata`

Portable Patch Panel files may include discovery metadata in `metadata`, but runtime registry state should live in a first-class table.

Recommended rule:

- `PatchPanel.metadata` may carry author-provided hints.
- `patch_panel_registry_entries` carries governed publication state and discoverability metadata.

This prevents a workflow file from granting itself published status.

## Acceptance Criteria

- Published Patch Panels can be discovered without loading every workflow file manually.
- Archived and superseded workflows remain inspectable.
- Registry mutation is permissioned and audited.
- Authorized participants can search by structured intent without needing graph-wide authority.
- Registry metadata does not store runtime card payloads or artifact content.
