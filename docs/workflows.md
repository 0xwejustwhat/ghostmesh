# Example Workflows

## Canonical Content Workflow

`examples/patchpanels/hello-world-patchpanel.yaml` demonstrates:

1. Source creates a Card.
2. Worker claims from `worker_input`.
3. Worker submits artifact references through `worker_output`.
4. Routing Validator accepts or rejects and selects an authorized exit pipe.
5. Accepted Cards route to `done`; rejected Cards route to `rejected`.
6. Sink records egress evidence.

Routing validators declare their allowed exits as `output_pipes`. When a validator
request omits an explicit `accepted` value, `config.accept_exits` determines which
selected exits record `accepted=true` on the ledger.

## Boundary Adapter Workflow

`examples/patchpanels/webhook-boundary-patchpanel.yaml` demonstrates:

1. GitHub issue webhook payload enters through a Source boundary.
2. The Source enforces authorization and deduplication.
3. Payload and metadata are mapped into a Card.
4. A notification Sink maps the approved Card into an external webhook payload.
5. The Sink records an external reference and egress idempotency key.

## Running The Canonical API Path

Register the Patch Panel:

```bash
curl -X POST http://localhost:8000/patchpanels \
  -H "Content-Type: application/json" \
  --data-binary @examples/patchpanels/hello-world-patchpanel.yaml
```

For YAML files, use the Python loader or convert to JSON before posting to the API.
