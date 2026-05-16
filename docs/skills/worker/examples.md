# Worker Examples

## Successful Local REST Run

1. Claim:

```bash
curl -X POST "$GHOSTMESH_URL/cards/claim" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: worker-1:worker_input:claim:demo-1" \
  -d '{"input_pipe":"worker_input","worker_id":"worker-1","lease_seconds":900}'
```

2. Inspect:

```bash
curl "$GHOSTMESH_URL/workers/leases/$LEASE_ID/context"
```

3. Submit:

```bash
curl -X POST "$GHOSTMESH_URL/cards/submit" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $CARD_ID:worker-1:submit:demo-1" \
  -d '{
    "lease_id": "'"$LEASE_ID"'",
    "output_pipe": "worker_output",
    "artifact_refs": [{
      "card_id": "'"$CARD_ID"'",
      "storage_ref": "git:working-tree:artifacts/'"$CARD_ID"'/draft.txt",
      "content_hash": "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "content_type": "text/plain",
      "size_bytes": 12,
      "metadata": {"role": "draft", "worker_id": "worker-1"}
    }]
  }'
```

## SDK Run

```python
from ghostmesh.artifacts import LocalGitArtifactStore
from ghostmesh.sdk import WorkerClient

client = WorkerClient("http://localhost:8000", worker_id="worker-1")
lease = client.claim(input_pipe="worker_input")
context = client.context(lease_id=lease["id"])
store = LocalGitArtifactStore("artifacts", repo_root=".")

artifact = client.upload_bytes(
    store,
    card_id=context["card"]["id"],
    data=b"draft output",
    filename="draft.txt",
    content_type="text/plain",
    metadata={"role": "draft"},
)
client.submit(lease["id"], output_pipe="worker_output", artifact_refs=[artifact])
```
