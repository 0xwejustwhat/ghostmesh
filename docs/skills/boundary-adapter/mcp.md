# Boundary Adapter MCP Reference

MCP may be used at the edge. MCP is not the internal runtime.

## `ghostmesh.boundary_source`

Input:

```json
{
  "patch_panel_id": "webhook_boundary",
  "source_id": "github_issue_source",
  "external_payload": {},
  "headers": {},
  "actor_token": "dev-webhook-token"
}
```

Output:

```json
{"card": {}, "deduplication_key": "delivery-1", "adapter": "github_issue_webhook"}
```

## `ghostmesh.boundary_sink`

Input:

```json
{
  "patch_panel_id": "webhook_boundary",
  "sink_id": "notification_sink",
  "card_id": "<card_id>",
  "external_response": {},
  "actor_token": "dev-egress-token"
}
```

Output:

```json
{
  "event": {},
  "external_reference": "<external_reference>",
  "egress_idempotency_key": "<key>",
  "adapter": "http_webhook_egress"
}
```
