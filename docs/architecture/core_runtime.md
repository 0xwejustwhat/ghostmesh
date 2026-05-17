# Core Runtime Architecture

Ghost Mesh is a graph-native accountability runtime. It owns Cards, buckets, leases,
events, validation, routing, and sink egress. It does not orchestrate agents.

Core rules:

- Patch Panels declare the graph.
- Cards carry work and lifecycle state.
- Buckets are locations reached through pipe bindings.
- Workers transform Cards through assigned pipes.
- Validators record judgment and route through declared exits.
- Sinks perform controlled egress and record external references.
- Runtime state is append-only evidence plus current Card location.

There must not be a parallel lifecycle controller for a subprocess. If a process needs
state, it needs a Card in a Patch Panel.
