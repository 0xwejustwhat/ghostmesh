# Workflow Architect Examples

## Register Patch Panel

```bash
curl -X POST "$GHOSTMESH_URL/patchpanels" \
  -H "Content-Type: application/json" \
  -d @patch-panel.json
```

## Propose And Promote Mutation

```bash
curl -X POST "$GHOSTMESH_URL/mutations" \
  -H "Content-Type: application/json" \
  -d '{"mutation_type":"route","proposed_by":"workflow_architect","payload":{"summary":"Route low confidence to review"}}'

curl -X POST "$GHOSTMESH_URL/mutations/$MUTATION_ID/validate" \
  -H "Content-Type: application/json" \
  -d '{"accepted":true,"validator_id":"mutation_validator","reason":"Shadow metrics improved"}'

curl -X POST "$GHOSTMESH_URL/mutations/$MUTATION_ID/promote" \
  -H "Content-Type: application/json" \
  -d '{"patch_panel": {}}'
```
