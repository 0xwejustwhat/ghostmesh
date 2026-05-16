# Mutation Cards

Use mutation records for changes to:

- prompts;
- workers;
- validators;
- routes;
- acceptance contracts;
- workflow versions.

Never mutate production directly. Propose, validate, then promote.

REST:

```json
{
  "mutation_type": "acceptance_contract",
  "proposed_by": "workflow_architect",
  "payload": {
    "summary": "Require source references on drafts",
    "patch_panel_id": "hello_world"
  }
}
```
