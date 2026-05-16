# Worker REST API Reference

## Claim

`POST /cards/claim`

Request:

```json
{
  "input_pipe": "worker_input",
  "worker_id": "worker-1",
  "lease_seconds": 900
}
```

Success response is a Lease:

```json
{
  "id": "<lease_id>",
  "card_id": "<card_id>",
  "node_id": "example_worker",
  "worker_id": "worker-1",
  "input_pipe": "worker_input",
  "claimed_at": "<iso_datetime>",
  "expires_at": "<iso_datetime>",
  "released_at": null
}
```

`404` means no claimable Card is available. Return idle.

## Context

`GET /workers/leases/{lease_id}/context`

Success response:

```json
{
  "lease": {},
  "card": {},
  "history": []
}
```

## Submit

`POST /cards/submit`

Request:

```json
{
  "lease_id": "<lease_id>",
  "output_pipe": "worker_output",
  "artifact_refs": [
    {
      "card_id": "<card_id>",
      "storage_ref": "git:working-tree:artifacts/<card_id>/draft.txt",
      "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "content_type": "text/plain",
      "size_bytes": 12,
      "metadata": {"role": "draft"}
    }
  ]
}
```

Success response is a list of stored `ArtifactReference` objects with IDs and `event_id`.

## Errors

- `404`: no work, missing lease, or missing Card.
- `409`: lease expired, released, or idempotency key reused for another operation.
- `422`: malformed payload, wrong pipe, artifact belongs to another Card, or acceptance contract rejected artifact references.
