# Intent-Driven Genesis Architecture

Genesis accepts structured intent through neutral `/genesis` APIs. Free-form prompt
parsing, chat UX, model choice, and worker tools live outside the Ghost Mesh runtime.

When a matching published workflow exists, Genesis launches a normal Card in that Patch
Panel. When no matching workflow exists, `/genesis/intents/{intent_id}/propose` creates a
normal Card in `system_pp_approval`.

`system_pp_approval` routes proposal Cards through:

```text
proposal_source
-> topological_validator
-> governance_reviewer
-> registry_publication_sink
```

The source node's declared output pipe determines the proposal Card's initial bucket.
The topological validator invokes `PatchPanelValidator().validate()` against the
candidate Patch Panel in the Card payload and chooses either the valid or invalid exit.
The governance reviewer is a standard routing validator with approval and rejection
exits. The registry publication sink reads the approved Card payload and writes the
published entry to `patch_panel_registry_entries`.

There is no proposal store. Proposal state is Card state and Card history.

At app startup, `SystemWorkflowBootstrapper` loads configured system Patch Panels from
`src/ghostmesh/defaults/patchpanels/` or operator-provided override paths. Seeding is
idempotent across repeated app creation and process restarts.
