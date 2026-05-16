# Human To AI Operating Path

Ghost Mesh is designed for gradual delegation.

## 1. Human Production

Humans perform production work and validation. The mesh records Cards, leases, artifacts, validation decisions, movements, and sink evidence.

## 2. AI Shadow

AI workers run on shadow Cards linked to production Cards. Shadow lanes cannot execute production sinks unless explicitly allowed. Operators compare acceptance rate, cost, latency, revision count, and validator scores.

## 3. Supervised AI Production

After shadow results are validated, AI workers may receive production leases for narrow pipes. Validators, including routing validators, remain explicit controls.

## 4. Exception-Based Oversight

Humans handle exceptions, policy decisions, low-confidence cases, failed movements, and promotion approvals. Workflow mutations continue through Mutation Cards, validation gates, and promotion gates.

## Non-Negotiables

- Workers do not own routing.
- Boundary adapters mediate external side effects.
- Learning Nodes propose; they do not mutate production directly.
- Patch Panels remain the source of workflow truth.
