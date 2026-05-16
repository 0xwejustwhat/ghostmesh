# Boundary Idempotency

## Source Dedupe

Source dedupe keys prevent duplicate external events from creating duplicate Cards.

Examples:

- `github:delivery:<X-GitHub-Delivery>`
- `github:issue:<repo>:<issue_number>`
- `slack:event:<event_id>`

When a duplicate is detected, return the existing Card. Do not create a second Card.

## Sink Egress Idempotency

Sink idempotency prevents duplicate external side effects.

Examples:

- `<card_id>:<sink_id>`
- `<card_id>:<sink_id>:<external_target>`

When egress already succeeded, return the recorded external reference. Do not publish twice.
