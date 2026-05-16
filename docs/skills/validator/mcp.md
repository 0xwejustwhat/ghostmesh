# Validator MCP Reference

## `ghostmesh.list_validator_cards`

Input:

```json
{"validator_id": "human_validator", "patch_panel_id": "hello_world"}
```

Output:

```json
{"cards": []}
```

## `ghostmesh.inspect_card`

Input:

```json
{"card_id": "<card_id>"}
```

Output:

```json
{"card": {}, "history": []}
```

## `ghostmesh.submit_validator_decision`

Input:

```json
{
  "validator_id": "human_validator",
  "card_id": "<card_id>",
  "patch_panel_id": "hello_world",
  "accepted": true,
  "score": 8,
  "reason": "Meets contract",
  "idempotency_key": "<card_id>:human_validator:decision:attempt-1"
}
```

Output:

```json
{"event": {}}
```
