# Worker MCP Reference

Ghost Mesh may expose MCP tools for workers. Tool names may be adapter-specific; prefer these canonical names when available.

## `ghostmesh.claim_card`

Input:

```json
{
  "worker_id": "worker-1",
  "input_pipe": "worker_input",
  "lease_seconds": 900,
  "idempotency_key": "worker-1:worker_input:claim:attempt-1"
}
```

Output:

```json
{"lease": {}}
```

## `ghostmesh.get_worker_context`

Input:

```json
{"lease_id": "<lease_id>"}
```

Output:

```json
{"lease": {}, "card": {}, "history": []}
```

## `ghostmesh.submit_artifact`

Input:

```json
{
  "lease_id": "<lease_id>",
  "output_pipe": "worker_output",
  "artifact_refs": [],
  "idempotency_key": "<card_id>:worker-1:submit:attempt-1"
}
```

Output:

```json
{"artifact_refs": []}
```

## `ghostmesh.renew_lease`

Input:

```json
{"lease_id": "<lease_id>", "lease_seconds": 900}
```

## `ghostmesh.release_lease`

Input:

```json
{"lease_id": "<lease_id>", "actor_id": "worker-1"}
```

If MCP tools are unavailable, use the REST flow.
