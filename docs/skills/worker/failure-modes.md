# Worker Failure Modes

## No Card Available

REST returns `404` from `/cards/claim`. Return idle. Do not create a Card.

## Lease Expired

REST returns `409`. Stop work and do not submit. Claim again only if instructed by the runtime.

## Missing Context

Release the lease and report:

```json
{
  "status": "failed",
  "reason": "missing_context",
  "details": "Card lacks required source text",
  "recommended_next_action": "Return to Source or request human triage"
}
```

## Artifact Store Failure

Do not submit inline artifact content to Ghost Mesh. Retry the store if safe, renew lease if needed, or release with `tool_failure`.

## Acceptance Contract Unclear

Do not guess. Release the lease or submit a failure artifact only if the workflow contract explicitly accepts failure artifacts.
