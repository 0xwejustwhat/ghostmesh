# Workflow Architect Skill

Use this skill when you are assigned to design or mutate Ghost Mesh workflows.

## Purpose

Create Patch Panels, buckets, routes, contracts, and node specs. Keep workflow logic out of workers. Propose changes through Mutation Cards, shadow evaluation and promotion gates.

## Required Inputs

- `base_url`: Ghost Mesh API base URL.
- Target `patch_panel_id` and version strategy.
- Workflow goal and domain constraints.
- Source/Sink boundary requirements.
- Acceptance requirements.
- Optional `mutation_id` when validating or promoting.

## Interface Order

1. MCP tools: `ghostmesh.register_patch_panel`, `ghostmesh.propose_mutation`, `ghostmesh.validate_mutation`, `ghostmesh.promote_mutation`.
2. REST API.
3. Local mock adapter only in development or tests.

## Patch Panel Generation Procedure

1. Define buckets.
2. Define nodes with types and pipes.
3. Define pipe bindings.
4. Define acceptance contracts.
5. Define deterministic edges and routing validator exits.
6. Define Source/Sink boundary contracts.
7. Validate graph mentally and with runtime registration.
8. Register Patch Panel.

REST:

```http
POST /patchpanels
Content-Type: application/json
```

```json
{
  "id": "example_workflow",
  "version": "1.0.0",
  "buckets": [{"id": "intake"}],
  "nodes": [
    {"id": "source", "type": "source", "output_pipes": ["source_output"]},
    {"id": "sink", "type": "sink", "input_pipes": ["sink_input"]}
  ],
  "pipe_bindings": {
    "source_output": {"node": "source", "direction": "output", "bucket": "intake"},
    "sink_input": {"node": "sink", "direction": "input", "bucket": "intake"}
  },
  "edges": [{"from": "source", "to": "sink", "on": "card_created"}]
}
```

## Mutation Procedure

Propose:

```http
POST /mutations
```

```json
{
  "mutation_type": "route",
  "proposed_by": "workflow_architect",
  "payload": {
    "reason": "Improve accepted route isolation",
    "patch_panel_id": "hello_world",
    "candidate_version": "1.1.0"
  }
}
```

Validate:

```http
POST /mutations/<mutation_id>/validate
```

```json
{
  "accepted": true,
  "validator_id": "mutation_validator",
  "reason": "Shadow metrics improved and graph remains valid."
}
```

Promote:

```http
POST /mutations/<mutation_id>/promote
```

```json
{"patch_panel": {}}
```

## Forbidden Actions

- Do not embed routing decisions inside Worker Nodes.
- Do not give Learning Nodes direct production mutation authority.
- Do not bypass validation or promotion gates.
- Do not make external systems the workflow source of truth.
- Do not make workers responsible for global graph knowledge.

See `patch-panel-generation.md`, `mutation-cards.md`, `shadow-lanes.md`, `promotion.md`, and `examples.md`.
