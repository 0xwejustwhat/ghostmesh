# Source Node Procedure

Source Nodes admit external events.

## Steps

1. Read external payload and headers.
2. Verify assigned authorization.
3. Compute dedupe key from the Source boundary contract.
4. Call `/boundaries/source` or `ghostmesh.boundary_source`.
5. Return existing or new Card ID.

## Required Evidence

- External system name.
- External delivery ID or dedupe key.
- Sender or service identity when available.
- Source node ID.
- Mapping result.

## Do Not

- Create Cards by writing to the database.
- Perform worker transformation.
- Decide downstream route.
