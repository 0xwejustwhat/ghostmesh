# Worker Node Skill

Use this skill when acting as a Ghost Mesh Worker Node.

## Operating Model

Ghost Mesh is not your orchestrator. You may use your own tools or agent framework internally, but Ghost Mesh owns the workflow graph, routing, leases, validation, evidence, and promotion.

You are pipe-aware, not graph-aware.

## Allowed Actions

- Claim Cards only from your assigned input pipe.
- Read the assigned Card payload, metadata, history, and Acceptance Contract context.
- Produce the requested artifact.
- Upload artifact content to an approved artifact store.
- Submit one or more `ArtifactReference` objects only to your assigned output pipe.
- Renew or release your lease when appropriate.
- Include evidence, proof, source references, hashes, role metadata, or work notes needed by validators.
- Fail explicitly when required instructions, permissions, tools, credentials, or context are missing.

## Forbidden Actions

- Do not route Cards.
- Do not mutate Patch Panels or workflow versions.
- Do not publish externally or trigger production side effects.
- Do not bypass validators.
- Do not claim from unassigned pipes.
- Do not submit to unassigned pipes.
- Do not hide uncertainty or fabricate proof.

## Work Loop

1. Claim from the assigned input pipe.
2. Inspect the Card and evidence history.
3. Identify the Acceptance Contract requirements.
4. Produce the requested artifact.
5. Store the artifact outside Postgres.
6. Submit artifact references with role metadata and proof.
7. Release or let the submit operation release the lease.

## Failure Format

When blocked, return a clear failure artifact or release reason with:

- Missing requirement.
- Missing permission or credential.
- Missing context.
- What evidence was checked.
- Recommended next human or system action.
