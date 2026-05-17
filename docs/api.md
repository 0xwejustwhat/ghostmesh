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

## Participant Identity

Protected governance endpoints accept `X-Ghostmesh-Participant`. This identifies the
participant being authorized. It is separate from runtime fields such as `worker_id`,
`validator_id`, and `actor_id`, which remain lease/event identity fields for MVP
compatibility.

## Participants And Permissions

Local/dev participant management:

- `GET /participants`
- `POST /participants`
- `POST /participants/{participant_id}/roles`
- `POST /participants/{participant_id}/permissions`
- `GET /participants/{participant_id}/permissions`

## Workers And Validators

- `GET /workers/leases/{lease_id}/context`
- `GET /validators/{validator_id}/cards?patch_panel_id=...`
- `GET /validators/cards/{card_id}`
- `POST /validators/{validator_id}/cards/{card_id}/decision`

## Node Execution

- `POST /nodes/source/execute`
- `POST /nodes/worker/execute`
- `POST /nodes/validator/execute`
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

## Patch Panel Registry

- `GET /registry/patchpanels`
- `POST /registry/patchpanels`
- `GET /registry/patchpanels/{entry_id}`
- `PATCH /registry/patchpanels/{entry_id}`
- `POST /registry/patchpanels/{entry_id}/archive`
- `POST /registry/patchpanels/{entry_id}/supersede`

Search supports exact filters such as `tag`, `input_type`, `output_type`,
`required_tool`, `risk_level`, and `owner_participant_id`.

## Intent-Driven Genesis

- `POST /genesis/intents`
- `GET /genesis/intents/{intent_id}`
- `POST /genesis/intents/{intent_id}/launch`
- `POST /genesis/intents/{intent_id}/propose`

Genesis accepts structured intent only. Free-form prompt parsing belongs outside the
runtime. When a missing workflow is proposed, `/genesis/intents/{intent_id}/propose`
creates a normal Card in `system_pp_approval`; validation, governance routing, rejection,
and registry publication proceed through `/nodes/validator/execute` and
`/nodes/sink/execute`.

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
