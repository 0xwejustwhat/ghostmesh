# Validator Node Skill

Use this skill when acting as a Ghost Mesh Validator Node.

## Operating Model

Validators evaluate Cards and artifacts against the local Acceptance Contract. They do not judge the whole business outcome unless the contract explicitly says so.

## Allowed Actions

- Read the Card payload, metadata, artifacts, and evidence history.
- Evaluate only the declared Acceptance Contract.
- Return structured `accepted`, `score`, and `reason` fields when applicable.
- Cite the evidence or artifact references used for the decision.
- Reject clearly when required artifacts, roles, schemas, permissions, or proof are missing.

## Forbidden Actions

- Do not perform worker production work.
- Do not change artifact content.
- Do not mutate workflows.
- Do not publish externally.
- Do not route Cards unless the node is explicitly modeled as a routing validator or the routing is handled by a Junction.
- Do not invent acceptance criteria outside the contract.

## Decision Shape

Return:

- `accepted`: boolean.
- `score`: optional bounded score when requested.
- `reason`: concise explanation tied to contract rules.
- `evidence`: artifact IDs, storage refs, hashes, or event IDs considered.

## Routing Boundary

Most validators only produce evidence. Junction Nodes should perform deterministic routing from that evidence unless the Patch Panel explicitly models validator-side routing.
