# Validator Decision Shapes

## Accept

```json
{
  "accepted": true,
  "score": 8,
  "reason": "Artifact has required role and sufficient evidence.",
  "evidence": ["artifact:<id>", "event:<id>"]
}
```

## Reject

```json
{
  "accepted": false,
  "score": 2,
  "reason": "Missing required role: draft.",
  "evidence": ["event:<id>"]
}
```

## Cannot Evaluate

Use rejection unless the workflow defines a separate triage status.

```json
{
  "accepted": false,
  "score": 0,
  "reason": "Cannot evaluate because the artifact reference is missing.",
  "evidence": []
}
```
