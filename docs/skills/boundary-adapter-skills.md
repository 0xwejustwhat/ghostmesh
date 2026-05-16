# Boundary Adapter Skill

Use this skill when acting as a Ghost Mesh Source or Sink boundary adapter.

## Operating Model

Source and Sink Nodes are thin boundary adapters, not workflow brains. They translate between Ghost Mesh and external systems while preserving authorization, deduplication, idempotency, and evidence.

## Source Nodes

Source Nodes only translate authorized external events into valid Cards.

They must:

- Verify the external event is authorized.
- Map payload fields into the Card shape declared by the boundary contract.
- Attach relevant metadata such as external system, sender, repository, channel, or delivery ID.
- Enforce the configured deduplication key.
- Record evidence of the ingress event.

They must not:

- Perform production work.
- Decide downstream routing.
- Bypass Patch Panel definitions.
- Admit unauthorized or malformed events.

## Sink Nodes

Sink Nodes only translate approved Cards or artifacts into external side effects.

They must:

- Verify the Card is ready for egress.
- Enforce the configured egress idempotency key.
- Perform only the side effect modeled by the Sink.
- Return external references, durable proofs, message IDs, URLs, receipt IDs, or transaction IDs.
- Record egress evidence in the Card history.

They must not:

- Do worker transformation work unless explicitly modeled as a Worker Node.
- Publish twice when the same egress idempotency key has already succeeded.
- Route Cards or mutate workflows.
- Treat external systems as the workflow source of truth.

## MCP Boundary Rule

MCP tools may be used at the edge for Source and Sink integration. MCP is not the internal Ghost Mesh runtime.
