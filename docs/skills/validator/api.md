# Validator REST API

## List Reviewable Cards

`GET /validators/{validator_id}/cards?patch_panel_id={patch_panel_id}`

Response:

```json
[
  {
    "id": "<card_id>",
    "workflow_version": "hello_world:1.0.0",
    "current_bucket": "validation_inbox",
    "payload": {},
    "metadata": {}
  }
]
```

## Inspect Card

`GET /validators/cards/{card_id}`

Response:

```json
{"card": {}, "history": []}
```

## Submit Decision

`POST /validators/{validator_id}/cards/{card_id}/decision`

Request:

```json
{
  "patch_panel_id": "hello_world",
  "accepted": true,
  "score": 8,
  "reason": "Meets contract"
}
```

Response is a `card_validated` event.

## Errors

- `404`: validator, Card, or Patch Panel not found.
- `409`: idempotency conflict.
- `422`: invalid score or invalid operation.
