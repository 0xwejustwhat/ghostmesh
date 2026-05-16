# Boundary Adapter Skill

Use this skill when you are assigned to a Ghost Mesh Source or Sink Node.

## Purpose

Source and Sink Nodes are thin boundary adapters. They are not workflow brains.

Sources translate authorized external events into valid Cards. Sinks translate approved Cards or artifacts into external side effects. External side effects are safely controlled only when mediated through Ghost Mesh Sink contracts or when durable proof is recorded.

## Required Inputs

Your runtime must provide:

- `base_url`: Ghost Mesh API base URL.
- `patch_panel_id`.
- `source_id` or `sink_id`.
- For Sources: external event payload, headers, and authorization material.
- For Sinks: `card_id`, external target details, and authorization material.
- `attempt_id` for stable idempotency.

## Interface Order

1. MCP tools: `ghostmesh.boundary_source`, `ghostmesh.boundary_sink`.
2. REST API: `/boundaries/source`, `/boundaries/sink`.
3. Local mock adapter only in development or tests.

Never write directly to Postgres. Never bypass Ghost Mesh to create Cards or record egress.

## Source Node Procedure

1. Receive external event.
2. Verify authorization using the boundary contract or assigned credential.
3. Compute or read the deduplication key.
4. Submit the event through Ghost Mesh Source boundary.
5. If the event was already admitted, return the existing Card ID.
6. Return Card ID, dedupe key, and adapter name.

REST call:

```http
POST /boundaries/source
Content-Type: application/json
```

```json
{
  "patch_panel_id": "<patch_panel_id>",
  "source_id": "<source_id>",
  "actor_token": "<assigned_boundary_token>",
  "headers": {
    "X-GitHub-Delivery": "delivery-123"
  },
  "external_payload": {
    "issue": {
      "title": "Bug",
      "body": "Details",
      "html_url": "https://github.com/org/repo/issues/123"
    }
  }
}
```

Expected success:

```json
{
  "card": {
    "id": "<card_id>",
    "payload": {},
    "metadata": {},
    "current_bucket": "<bucket>"
  },
  "deduplication_key": "delivery-123",
  "adapter": "github_issue_webhook"
}
```

MCP call:

```json
{
  "tool": "ghostmesh.boundary_source",
  "input": {
    "patch_panel_id": "<patch_panel_id>",
    "source_id": "<source_id>",
    "actor_token": "<assigned_boundary_token>",
    "headers": {},
    "external_payload": {}
  }
}
```

## Sink Node Procedure

1. Verify the Card is authorized for egress by the assigned workflow state and Sink contract.
2. Compute the egress idempotency key.
3. If egress already succeeded, return the recorded external reference.
4. Perform only the modeled external side effect.
5. Capture the external reference or proof.
6. Record egress through Ghost Mesh Sink boundary.
7. Return event ID, external reference, idempotency key, and adapter name.

REST call:

```http
POST /boundaries/sink
Content-Type: application/json
```

```json
{
  "patch_panel_id": "<patch_panel_id>",
  "sink_id": "<sink_id>",
  "card_id": "<card_id>",
  "actor_token": "<assigned_boundary_token>",
  "external_response": {
    "message_ts": "slack://C123/1710000000.000001",
    "external_reference": "slack://C123/1710000000.000001"
  }
}
```

Expected success:

```json
{
  "event": {
    "id": "<event_id>",
    "card_id": "<card_id>",
    "event_type": "sink_executed"
  },
  "external_reference": "slack://C123/1710000000.000001",
  "egress_idempotency_key": "<card_id>:<sink_id>",
  "adapter": "http_webhook_egress"
}
```

MCP call:

```json
{
  "tool": "ghostmesh.boundary_sink",
  "input": {
    "patch_panel_id": "<patch_panel_id>",
    "sink_id": "<sink_id>",
    "card_id": "<card_id>",
    "actor_token": "<assigned_boundary_token>",
    "external_response": {}
  }
}
```

## Failure Format

```json
{
  "status": "failed",
  "node_id": "<source_or_sink_id>",
  "reason": "unauthorized|duplicate|mapping_failed|external_side_effect_failed|missing_external_reference",
  "dedupe_or_idempotency_key": "<key>",
  "external_reference": null,
  "details": "specific, verifiable explanation"
}
```

## Forbidden Actions

- Do not perform production work unless explicitly modeled as a Worker Node.
- Do not route Cards.
- Do not mutate workflows.
- Do not skip dedupe or idempotency.
- Do not hide external side effects from Ghost Mesh evidence.
- Do not use MCP as the internal Ghost Mesh runtime.

See `source-node.md`, `sink-node.md`, `api.md`, `mcp.md`, `idempotency.md`, and `examples.md`.
