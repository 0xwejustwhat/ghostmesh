# Patch Panel Generation

## Checklist

- At least one Source and one Sink.
- Source has no incoming edges.
- Sink has no outgoing edges.
- Every declared pipe has a binding.
- Every binding points to a declared bucket.
- Workers have explicit input and output pipes.
- Validators have clear Acceptance Contracts.
- Junction routes are deterministic.
- Source/Sink boundaries define authorization and idempotency.

## Minimal Shape

```json
{
  "id": "workflow_id",
  "version": "1.0.0",
  "buckets": [],
  "nodes": [],
  "edges": [],
  "pipe_bindings": {},
  "acceptance_contracts": []
}
```
