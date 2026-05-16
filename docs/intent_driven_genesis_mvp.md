# Intent-Driven Genesis MVP

Ghost Mesh accepts structured intent through generic `/genesis` APIs. The caller can be a CLI, webhook, integration, conversational client, script, or service. The runtime does not need to know which kind.

## Submit Structured Intent

```http
POST /genesis/intents
X-Ghostmesh-Participant: intent-operator
```

```json
{
  "requested_by": "intent-operator",
  "deduplication_key": "customer-123:launch-outreach:2026-05-16",
  "goal": "launch outreach campaign",
  "input_type": "campaign_brief",
  "desired_outputs": ["approved_message_sequence"],
  "tags": ["sales", "outreach"],
  "constraints": {
    "risk_level": "medium",
    "max_latency": "days",
    "requires_human_approval": true
  },
  "launch_if_existing": true,
  "propose_if_missing": true
}
```

The endpoint searches the Patch Panel registry using exact metadata filters and records audit evidence. It does not parse free-form prompts.

## Launch An Existing Workflow

```http
POST /genesis/intents/{intent_id}/launch
X-Ghostmesh-Participant: intent-operator
```

```json
{
  "registry_entry_id": "00000000-0000-0000-0000-000000000000"
}
```

The participant must have `card:create` in the selected Patch Panel scope.

## Propose A New Workflow

```http
POST /genesis/intents/{intent_id}/propose
X-Ghostmesh-Participant: workflow-architect
```

The body contains a normal Patch Panel definition plus registry metadata. The proposal is validated and stored for review; it is not published until a separate reviewer approves it.
