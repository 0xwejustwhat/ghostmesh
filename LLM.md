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

## Protocol Symmetry (REST & MCP)

- Ghost Mesh treats REST API paths and MCP tool registration hooks as identical protocol gateways. They run over identical domain models, data engines, and compliance policies.
- DO NOT write specialized data persistence overrides inside tool routers. Tool controllers invoke core `runtime`, `NodeExecutor`, or boundary adapter primitives directly.
- MCP tools must not bypass participant authorization, Card movement rules, validation contracts, sink constraints, or registry publication safeguards.

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

## 5. Participant Neutrality

- Human, agent, script, service, and integration identities are all `Participant` records.
- DO NOT grant authority based on interface type, model type, or caller transport.
- Authorization must flow through participant id, permission, scope, and active role or grant state.

## 6. Shared Bootstrapping

- FastAPI startup and `ghostmesh mcp-server` stdio startup must use the same shared system initializer.
- The initializer seeds system Patch Panels and the root operator participant idempotently.
- DO NOT add one-off bootstrap logic to protocol routers, MCP tools, or public API endpoints.

## 7. Graph-Native Onboarding

- Participant expansion belongs in `system_agent_registration` as Cards, validators, and an authorized sink.
- DO NOT create custom onboarding stores, procedural approval tables, or side-channel participant lifecycle managers.
- The authority provisioner sink may write participants and role grants only after declared validation and admin-review history exists on the Card.
