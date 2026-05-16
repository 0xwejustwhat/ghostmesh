# Ghost Mesh Agent Skills

These files are operational playbooks for agents participating in Ghost Mesh.

They are not architecture essays. Each role directory contains a `SKILL.md` that tells an agent what inputs it needs, which interface to prefer, what exact calls to make, what response shape to expect, how to form idempotency keys, how to fail, and what actions are forbidden.

Use interfaces in this order unless the runtime assigns a specific interface:

1. MCP tools, if available.
2. Ghost Mesh SDK, if available for the role.
3. REST API, if available.
4. Local mock adapter, only in development or tests.

Never bypass Ghost Mesh runtime state by writing directly to Postgres. The runtime owns leases, movement, idempotency, and auditability.

## Skills

- `worker/SKILL.md`: claim Cards, produce artifacts, submit artifact references.
- `validator/SKILL.md`: inspect review queues and submit decisions.
- `boundary-adapter/SKILL.md`: admit external events and execute controlled egress.
- `workflow-architect/SKILL.md`: generate Patch Panels and propose mutations safely.
