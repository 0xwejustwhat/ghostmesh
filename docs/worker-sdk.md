# Worker SDK

The Python SDK exposes pipe-aware worker operations. It deliberately does not expose graph routing controls.

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

client.submit(
    lease_id=lease["id"],
    output_pipe="worker_output",
    artifact_refs=[artifact],
)
```

Workers should:

- Claim only from their assigned input pipe.
- Submit only to their assigned output pipe.
- Renew or release leases explicitly.
- Upload content to an artifact store before submit.
- Include evidence in artifact metadata where useful.
- Fail explicitly when required context or permissions are missing.

Workers must not route Cards, mutate Patch Panels, execute production egress, or bypass validators.
