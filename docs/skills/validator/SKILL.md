# Validator Node Skill

Use this skill when you are assigned to a Ghost Mesh Validator Node.

## Purpose

Evaluate Cards and artifacts against the assigned Acceptance Contract. Return structured evidence. Do not perform worker production work.

## Required Inputs

- `base_url`: Ghost Mesh API base URL.
- `validator_id`.
- `patch_panel_id`.
- Optional `auth_token`.
- `card_id`, when assigned directly.
- Optional `attempt_id`.

## Interface Order

1. MCP tools: `ghostmesh.list_validator_cards`, `ghostmesh.inspect_card`, `ghostmesh.submit_validator_decision`.
2. REST API.
3. Local mock adapter only in development or tests.

## Review Queue Procedure

REST:

```http
GET /validators/<validator_id>/cards?patch_panel_id=<patch_panel_id>
```

MCP:

```json
{
  "tool": "ghostmesh.list_validator_cards",
  "input": {
    "validator_id": "<validator_id>",
    "patch_panel_id": "<patch_panel_id>"
  }
}
```

If the queue is empty, return idle.

## Inspect Procedure

REST:

```http
GET /validators/cards/<card_id>
```

Expected response:

```json
{
  "card": {
    "id": "<card_id>",
    "payload": {},
    "metadata": {},
    "current_bucket": "<bucket>"
  },
  "history": []
}
```

## Decision Procedure

Evaluate only against the Acceptance Contract and available evidence.

REST:

```http
POST /validators/<validator_id>/cards/<card_id>/decision
Idempotency-Key: <card_id>:<validator_id>:decision:<attempt_id>
Content-Type: application/json
```

```json
{
  "patch_panel_id": "<patch_panel_id>",
  "accepted": true,
  "score": 9,
  "reason": "Artifact includes required draft role and evidence."
}
```

Expected response:

```json
{
  "id": "<event_id>",
  "card_id": "<card_id>",
  "event_type": "card_validated",
  "actor_id": "<validator_id>",
  "payload": {
    "accepted": true,
    "reason": "Artifact includes required draft role and evidence."
  }
}
```

MCP:

```json
{
  "tool": "ghostmesh.submit_validator_decision",
  "input": {
    "validator_id": "<validator_id>",
    "card_id": "<card_id>",
    "patch_panel_id": "<patch_panel_id>",
    "accepted": true,
    "score": 9,
    "reason": "Artifact includes required draft role and evidence.",
    "idempotency_key": "<card_id>:<validator_id>:decision:<attempt_id>"
  }
}
```

## Decision Shape

```json
{
  "accepted": true,
  "score": 9,
  "reason": "specific contract-based reason",
  "evidence": ["artifact_id_or_event_id"]
}
```

## Failure Decision

Reject when required evidence is missing:

```json
{
  "accepted": false,
  "score": 0,
  "reason": "Missing required artifact role: draft",
  "evidence": []
}
```

## Forbidden Actions

- Do not change artifact content.
- Do not perform worker production work.
- Do not publish externally.
- Do not mutate workflows.
- Do not invent acceptance criteria.
- Do not route Cards unless explicitly modeled as a routing validator or Junction.

See `api.md`, `mcp.md`, `decision-shapes.md`, and `examples.md`.
