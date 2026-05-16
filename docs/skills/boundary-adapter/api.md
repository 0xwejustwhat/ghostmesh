# Boundary Adapter REST API

## Source

`POST /boundaries/source`

Request:

```json
{
  "patch_panel_id": "webhook_boundary",
  "source_id": "github_issue_source",
  "external_payload": {},
  "headers": {},
  "actor_token": "dev-webhook-token"
}
```

Response:

```json
{
  "card": {},
  "deduplication_key": "delivery-1",
  "adapter": "github_issue_webhook"
}
```

## Sink

`POST /boundaries/sink`

Request:

```json
{
  "patch_panel_id": "webhook_boundary",
  "sink_id": "notification_sink",
  "card_id": "<card_id>",
  "external_response": {
    "message_ts": "slack://C123/1710000000.000001"
  },
  "actor_token": "dev-egress-token"
}
```

Response:

```json
{
  "event": {},
  "external_reference": "slack://C123/1710000000.000001",
  "egress_idempotency_key": "<card_id>:notification_sink",
  "adapter": "http_webhook_egress"
}
```

## Errors

- `422`: authorization failed, mapping path missing, wrong node type, or target workflow mismatch.
- `404`: Patch Panel, Card, or node not found.
- `409`: idempotency conflict.
