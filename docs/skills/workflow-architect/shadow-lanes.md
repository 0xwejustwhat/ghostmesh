# Shadow Lanes

Use shadow lanes to audition worker or process changes without production effects.

## Procedure

1. Select production Card.
2. Create shadow Card with candidate ID.
3. Run candidate worker/process.
4. Prevent production Sink execution.
5. Record metrics.
6. Compare acceptance, cost, latency, revisions, and scores.

REST:

```json
{
  "production_card_id": "<card_id>",
  "candidate_id": "candidate-worker",
  "sample_rate": 1,
  "max_parallel": 1
}
```
