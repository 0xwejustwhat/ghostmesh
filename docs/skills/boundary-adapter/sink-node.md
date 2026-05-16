# Sink Node Procedure

Sink Nodes perform controlled egress.

## Steps

1. Confirm assigned `card_id` and `sink_id`.
2. Inspect Card history if your runtime gives access.
3. Verify egress is allowed by the Sink contract.
4. Compute egress idempotency key.
5. Perform the external side effect once.
6. Capture external reference or durable proof.
7. Call `/boundaries/sink` or `ghostmesh.boundary_sink`.
8. Return the Ghost Mesh event and external reference.

## Required Evidence

- External reference, message ID, URL, receipt ID, transaction ID, or proof.
- Egress idempotency key.
- External target.
- Sink node ID.

## Do Not

- Publish twice for the same idempotency key.
- Do worker transformation.
- Route Cards.
- Treat the external system as the workflow source of truth.
