# Boundary Adapter Examples

## GitHub Issue Source

```bash
curl -X POST "$GHOSTMESH_URL/boundaries/source" \
  -H "Content-Type: application/json" \
  -d '{
    "patch_panel_id": "webhook_boundary",
    "source_id": "github_issue_source",
    "actor_token": "dev-webhook-token",
    "headers": {"X-GitHub-Delivery": "delivery-1"},
    "external_payload": {
      "issue": {
        "title": "Boundary adapters",
        "body": "Wire Source and Sink edges.",
        "html_url": "https://github.com/acme/ghostmesh/issues/7"
      },
      "repository": {"full_name": "acme/ghostmesh"},
      "sender": {"login": "octocat"}
    }
  }'
```

## Notification Sink

```bash
curl -X POST "$GHOSTMESH_URL/boundaries/sink" \
  -H "Content-Type: application/json" \
  -d '{
    "patch_panel_id": "webhook_boundary",
    "sink_id": "notification_sink",
    "card_id": "'"$CARD_ID"'",
    "actor_token": "dev-egress-token",
    "external_response": {"message_ts": "slack://C123/1710000000.000001"}
  }'
```
