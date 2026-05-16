# REST API

Run locally with:

```bash
poetry run uvicorn ghostmesh.api.main:app --reload
```

OpenAPI is available at `/docs` when the FastAPI app is running.

## Runtime

- `GET /health`
- `GET /health/config`
- `GET /patchpanels`
- `POST /patchpanels`
- `GET /cards`
- `POST /cards`
- `POST /cards/claim`
- `POST /cards/submit`
- `POST /leases/{lease_id}/renew`
- `POST /leases/{lease_id}/release`
- `POST /leases/expire`
- `POST /cards/{card_id}/validate`
- `POST /cards/{card_id}/move`
- `GET /cards/{card_id}/history`

Idempotent mutation endpoints accept the `Idempotency-Key` header.

## Workers And Validators

- `GET /workers/leases/{lease_id}/context`
- `GET /validators/{validator_id}/cards?patch_panel_id=...`
- `GET /validators/cards/{card_id}`
- `POST /validators/{validator_id}/cards/{card_id}/decision`

## Node Execution

- `POST /nodes/source/execute`
- `POST /nodes/worker/execute`
- `POST /nodes/validator/human/execute`
- `POST /nodes/junction/execute`
- `POST /nodes/sink/execute`

## Boundary Adapters

- `POST /boundaries/source`
- `POST /boundaries/sink`

Source boundaries map authorized external events into Cards and deduplicate with configured keys. Sink boundaries map approved Cards into external side effects and record external references plus egress idempotency keys.

## Shadow And Mutations

- `POST /shadows`
- `POST /shadows/{link_id}/complete`
- `POST /mutations`
- `POST /mutations/{mutation_id}/validate`
- `POST /mutations/{mutation_id}/promote`

## Operator Views

- `GET /ops/topology/{patch_panel_id}`
- `GET /ops/cards/by-bucket`
- `GET /ops/buckets/load`
- `GET /ops/leases/active`
- `GET /ops/workers/activity`
- `GET /ops/validators/decisions`
- `GET /ops/workflow-versions`
- `GET /ops/failed-movements`
- `GET /ops/metrics`
- `GET /ops/dashboard/{patch_panel_id}`
