# Ghost Mesh LLM Context Guardrails

## Core Invariants

- Ghost Mesh is a headless Card runtime, not an agent orchestration framework.
- Humans, agents, scripts, services, and integrations are all participants. Interface type never grants authority.
- Cards are the lifecycle state carrier. Card location, Card payload, and Card history are the source of truth for process state.
- Cards move exclusively through buckets reached by declared node output pipes.
- Validators choose declared exits. Sinks perform controlled egress. Workers do not route, approve, publish, or mutate production state directly.

## Strict Negative Constraints

- DO NOT build custom database tables or out-of-band state logic blocks for subprocess lifecycle tracking.
- DO NOT create procedural branching managers outside standard Source, Worker, Validator, Sink, Learning, or Subworkflow nodes.
- DO NOT special-case humans versus agents in runtime flow. Use participant roles, permissions, scopes, and tokens.
- DO NOT publish Patch Panels from Genesis or Registry helper code. Publication belongs to an authorized Sink node.
- DO NOT add side-channel proposal stores. A proposed Patch Panel is a Card in `system_pp_approval`.

## Vocabulary Anchors

- Patch Panel: declarative workflow graph containing nodes, buckets, pipes, edges, and contracts.
- Card: unit of work moving through a Patch Panel.
- Bucket: declared Card location, reached through pipe bindings.
- Node: executable role in the graph. Node type controls behavior, not actor identity.
- Validator: standard node that records judgment and may route through declared output pipes.
- Sink: controlled egress node that records side effects and external references.
- Registry: searchable index of governed Patch Panel versions.

## Package Boundaries

- `src/ghostmesh/domain`: Pydantic domain models and vocabulary. Keep this declarative.
- `src/ghostmesh/runtime`: generic Card, lease, event, movement, validation, and persistence mechanics.
- `src/ghostmesh/registry`: discoverability and publication index. It must not own proposal lifecycle state.
- `src/ghostmesh/genesis`: structured intent ingress and registry discovery. It may create proposal Cards, but it must not validate, approve, reject, or publish them.
- `src/ghostmesh/nodes`: node execution adapters over runtime primitives. System workflow behavior belongs here when it is still generic node behavior.
