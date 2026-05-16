# Validator Examples

## REST Decision

```bash
curl "$GHOSTMESH_URL/validators/human_validator/cards?patch_panel_id=hello_world"
curl "$GHOSTMESH_URL/validators/cards/$CARD_ID"
curl -X POST "$GHOSTMESH_URL/validators/human_validator/cards/$CARD_ID/decision" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: $CARD_ID:human_validator:decision:demo-1" \
  -d '{
    "patch_panel_id": "hello_world",
    "accepted": true,
    "score": 9,
    "reason": "Required draft artifact is present and supported by evidence."
  }'
```

## Rejection

```json
{
  "patch_panel_id": "hello_world",
  "accepted": false,
  "score": 1,
  "reason": "Artifact reference has no required role metadata."
}
```
