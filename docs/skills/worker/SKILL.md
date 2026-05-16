# Worker Node Skill

Use this skill when you are assigned to a Ghost Mesh Worker Node.

## Purpose

You transform one Card into one or more artifact references. Ghost Mesh is not your orchestrator. You are pipe-aware, not graph-aware. The Patch Panel owns routing.

## Required Inputs

Your runtime must provide:

- `base_url`: Ghost Mesh API base URL, for example `http://localhost:8000`.
- `worker_id`: your worker identity.
- `input_pipe`: the only pipe you may claim from.
- `output_pipe`: the only pipe you may submit to.
- `lease_seconds`: requested lease duration, commonly `900`.
- `artifact_store`: approved store or upload helper.
- Optional `auth_token`: bearer token if the API requires it.
- Optional `attempt_id`: stable unique ID for this work attempt.

## Available Interfaces

Use these in order unless instructed otherwise:

1. MCP tools: `ghostmesh.claim_card`, `ghostmesh.get_worker_context`, `ghostmesh.submit_artifact`, `ghostmesh.renew_lease`, `ghostmesh.release_lease`.
2. Python SDK: `ghostmesh.sdk.WorkerClient`.
3. REST API: `/cards/claim`, `/workers/leases/{lease_id}/context`, `/cards/submit`, `/leases/{lease_id}/renew`, `/leases/{lease_id}/release`.
4. Local mock adapter only in development or tests.

Never write directly to Postgres.

## MCP Tool Flow

Claim work:

```json
{
  "tool": "ghostmesh.claim_card",
  "input": {
    "worker_id": "<worker_id>",
    "input_pipe": "<input_pipe>",
    "lease_seconds": 900,
    "idempotency_key": "<worker_id>:<input_pipe>:claim:<attempt_id>"
  }
}
```

Expected success:

```json
{
  "lease": {
    "id": "<lease_id>",
    "card_id": "<card_id>",
    "node_id": "<worker_node_id>",
    "worker_id": "<worker_id>",
    "input_pipe": "<input_pipe>",
    "expires_at": "<iso_datetime>"
  }
}
```

If no Card is available, return idle. Do not invent work.

Inspect context:

```json
{
  "tool": "ghostmesh.get_worker_context",
  "input": {
    "lease_id": "<lease_id>"
  }
}
```

Expected success:

```json
{
  "lease": {},
  "card": {
    "id": "<card_id>",
    "payload": {},
    "metadata": {},
    "current_bucket": "<bucket>"
  },
  "history": []
}
```

Submit artifact references:

```json
{
  "tool": "ghostmesh.submit_artifact",
  "input": {
    "lease_id": "<lease_id>",
    "output_pipe": "<output_pipe>",
    "artifact_refs": [
      {
        "card_id": "<card_id>",
        "storage_ref": "git:working-tree:artifacts/<card_id>/draft.md",
        "content_hash": "sha256:<64_hex_chars>",
        "content_type": "text/markdown",
        "size_bytes": 1234,
        "metadata": {
          "role": "draft",
          "worker_id": "<worker_id>",
          "tools_used": [],
          "notes": "short evidence summary"
        }
      }
    ],
    "idempotency_key": "<card_id>:<worker_id>:submit:<attempt_id>"
  }
}
```

## REST API Flow

Claim:

```http
POST /cards/claim
Idempotency-Key: <worker_id>:<input_pipe>:claim:<attempt_id>
Content-Type: application/json
```

```json
{
  "input_pipe": "<input_pipe>",
  "worker_id": "<worker_id>",
  "lease_seconds": 900
}
```

Inspect:

```http
GET /workers/leases/<lease_id>/context
```

Submit:

```http
POST /cards/submit
Idempotency-Key: <card_id>:<worker_id>:submit:<attempt_id>
Content-Type: application/json
```

```json
{
  "lease_id": "<lease_id>",
  "output_pipe": "<output_pipe>",
  "artifact_refs": [
    {
      "card_id": "<card_id>",
      "storage_ref": "git:working-tree:artifacts/<card_id>/draft.md",
      "content_hash": "sha256:<64_hex_chars>",
      "content_type": "text/markdown",
      "size_bytes": 1234,
      "metadata": {
        "role": "draft",
        "worker_id": "<worker_id>",
        "proof": "how the output was produced"
      }
    }
  ]
}
```

Renew:

```http
POST /leases/<lease_id>/renew
Idempotency-Key: <lease_id>:renew:<attempt_id>
```

```json
{"lease_seconds": 900}
```

Release:

```http
POST /leases/<lease_id>/release
Idempotency-Key: <lease_id>:release:<attempt_id>
```

```json
{"actor_id": "<worker_id>"}
```

## Work Loop

1. Claim from `input_pipe`.
2. If no work is available, return idle.
3. Inspect the lease context.
4. Read the Card payload, metadata, and history.
5. Identify artifact requirements from the assigned task or Acceptance Contract context.
6. Produce the artifact.
7. Store artifact content in the approved artifact store.
8. Compute `sha256:<64_hex_chars>`.
9. Submit `artifact_refs` to `output_pipe`.
10. If blocked before submit, release the lease with a failure reason or submit a failure artifact only if the workflow expects one.

## Failure Format

When blocked, return or record:

```json
{
  "status": "failed",
  "worker_id": "<worker_id>",
  "card_id": "<card_id>",
  "lease_id": "<lease_id>",
  "reason": "missing_context|missing_permission|invalid_card|tool_failure|contract_unclear",
  "details": "specific, verifiable explanation",
  "evidence_checked": ["event_or_artifact_ids"],
  "recommended_next_action": "what a human or operator should do"
}
```

## What Not To Do

- Do not route Cards.
- Do not mutate Patch Panels or workflow versions.
- Do not publish externally or trigger production side effects.
- Do not bypass validators.
- Do not claim from unassigned pipes.
- Do not submit to unassigned pipes.
- Do not fabricate proof.

See `api.md`, `mcp.md`, `examples.md`, and `failure-modes.md` for role-specific details.
