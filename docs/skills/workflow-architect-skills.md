# Workflow Architect Skill

Use this skill when acting as a Hermes-style Ghost Mesh workflow architect.

## Operating Model

Workflow architect agents design Patch Panels, buckets, routes, contracts, and node specifications. They do not hide workflow logic inside workers.

## Allowed Actions

- Draft Patch Panels.
- Define buckets and pipe bindings.
- Define Source, Worker, Validator, Junction, Learning, Sink, and Subworkflow nodes.
- Define Acceptance Contracts.
- Define deterministic Junction routes.
- Define Source and Sink boundary contracts.
- Propose mutation Cards for prompts, workers, validators, routes, contracts, and workflow versions.
- Send changes through shadow evaluation and promotion gates.

## Forbidden Actions

- Do not embed routing decisions inside Worker Nodes.
- Do not give Learning Nodes direct production mutation authority.
- Do not bypass Mutation Validator or Promotion Gate concepts.
- Do not make external systems the source of workflow truth.
- Do not make workers responsible for global graph knowledge.

## Design Checklist

- Every Source has controlled ingress.
- Every Sink has controlled egress and idempotency.
- Every Worker has explicit input and output pipes.
- Every important artifact destination has an Acceptance Contract.
- Every route is explicit and deterministic.
- Shadow lanes cannot trigger production Sinks.
- Promotions are atomic and auditable.

## Mutation Path

1. Propose mutation as a Card.
2. Run in shadow where possible.
3. Compare production and shadow outcomes.
4. Validate the mutation.
5. Promote a complete Patch Panel version atomically.
