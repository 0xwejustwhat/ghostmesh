# Intent-Driven Genesis Architecture

## Purpose

Intent-driven genesis is the neutral Ghost Mesh pattern for turning structured external intent into Cards, Patch Panel discovery, and governed workflow proposals.

The runtime must not know, name, or privilege any specific conversational agent, LLM framework, assistant brand, or worker implementation. External clients may include chat agents, scripts, webhooks, CLIs, MCP tools, or manual API callers. They all interact with the same headless engine through uniform protocols and scoped participant permissions.

## Core Principle

```text
External clients submit intent.
Intent operators admit bounded work.
Workflow architects design and propose.
Patch Panels govern.
Validators judge.
The runtime enforces.
Reviewers promote.
```

No agent-specific name should appear in API paths, database role templates, core tables, or built-in workflow primitives.

## Functional Roles

### Intent Operator

The Intent Operator handles structured ingress from conversational sandboxes, automation systems, APIs, or manual callers.

Typical grants:

- `card:create` within designated intent ingress buckets
- `patch_panel:discover` when intake may reuse existing workflows

The role does not imply graph design authority unless paired with a separate Workflow Architect role.

### Workflow Architect

The Workflow Architect resolves process gaps by querying the registry and proposing workflow topologies.

Typical grants:

- `patch_panel:discover`
- `patch_panel:create`
- `patch_panel:edit_draft`
- `bucket:create`
- `node:create`
- `edge:create`
- `pipe_binding:create`
- `mutation:propose`
- `shadow:create`

The role should not include `mutation:promote`, `patch_panel:publish_version`, `sink:execute`, or `permission:grant` by default.

## What External Clients May Do

Depending on scoped permissions, any participant or external client may:

- submit structured intent
- discover Patch Panels
- create Cards in designated ingress scopes
- lease generative design work from an input pipe
- submit candidate Patch Panel proposals
- request governance approval
- launch shadow auditions

## What External Clients Must Not Do By Default

External clients should not:

- bypass Patch Panel validation
- embed Patch Panel authority inside worker implementation
- self-escalate permissions
- approve their own production mutations
- publish workflows directly
- execute production sinks unless separately granted sink authority
- route Cards outside declared Patch Panel edges

## MVP Request Shape

The first implementation should accept structured intent so the Ghost Mesh mechanics can be proven independently of any particular LLM, prompt stack, or agent runtime.

Suggested request:

```yaml
intent:
  requested_by: participant_id
  deduplication_key: customer-123:launch-linkedin-outreach:2026-05-16
  goal: launch linkedin outreach campaign
  input_type: campaign_goal
  desired_outputs:
    - approved_message_sequence
    - lead_list
  tags:
    - sales
    - outreach
  constraints:
    risk_level: medium
    max_latency: days
    requires_human_approval: true
  launch_if_existing: true
  propose_if_missing: true
```

The endpoint does not care whether the caller is a chat agent, a `curl` command, an n8n webhook, or an MCP client.

## Flow A: Existing Workflow Found

```text
structured intent
-> authorize participant for patch_panel:discover
-> search Patch Panel registry
-> select published candidate
-> authorize participant for card:create in ingress/workflow scope
-> create Card in source bucket
-> emit audit events
```

The participant does not need graph-wide authority. It only needs discovery and card creation in the relevant scope.

## Flow B: No Suitable Workflow Found

```text
structured intent
-> authorize participant for patch_panel:discover
-> no suitable registry match
-> create a design task in the genesis workflow
-> external workflow architect worker leases the task
-> worker submits candidate Patch Panel proposal
-> run schema and graph validation
-> store proposal and validation report
-> request governance review
```

The proposed workflow is not production until a separate participant approves or promotes it.

## Flow C: Workflow Improvement Detected

```text
observability evidence
-> Learning or Workflow Architect participant proposes mutation
-> shadow lane auditions change
-> mutation validator records evidence
-> reviewer approves promotion
-> registry supersedes old version
```

This preserves the Ghost Mesh principle that every improvement must audition.

## External Worker Implementations

A generative designer seat can exist in a Patch Panel like any other worker seat:

```yaml
nodes:
  - id: generative_designer_seat
    type: worker
    input_pipes:
      - intent_input
    output_pipes:
      - proposal_output
    config:
      mode: workflow_design
```

Any authorized external conversational agent provider can lease tasks from `intent_input`. Its prompting rules, local tools, model choices, tool-calling mechanics, and SKILL.md configuration live outside the Ghost Mesh runtime. The worker receives bounded input and submits artifact references or typed proposal payloads. The Patch Panel, not the worker, decides where the output goes next.

## Example Genesis Patch Panel

Suggested minimal topology:

```text
Intent Source
-> Generative Designer Seat
-> Patch Panel Validator
-> Governance Reviewer
-> Registry Publication Sink
```

Example graph sketch:

```yaml
name: system_workflow_genesis
buckets:
  - id: intent_intake
  - id: topology_proposals
  - id: governance_review
nodes:
  - id: generative_designer_seat
    type: worker
    input_pipes:
      - intent_input
    output_pipes:
      - proposal_output
```

Possible buckets:

- `intent_intake`
- `topology_proposals`
- `validated_workflow_proposals`
- `governance_review`
- `published_registry_updates`
- `rejected_proposals`

Possible acceptance contracts:

- Candidate Patch Panel must parse as a `PatchPanel`.
- Graph validation must pass without unreachable nodes or illegal source/sink edges.
- Worker nodes must use pipe bindings.
- Sink nodes must declare egress contracts.
- Shadow lanes must not allow production egress.
- Registry metadata must include tags, input types, output types, risk level, and owner.

## Proposed APIs

```text
POST /genesis/intents
GET /genesis/intents/{intent_id}
POST /genesis/intents/{intent_id}/launch
POST /genesis/intents/{intent_id}/propose
```

These should be thin service endpoints over existing runtime, registry, proposal, and authorization services. They must not become a second orchestration system or an agent-specific namespace.

## Audit Events

Intent-driven genesis should emit audit evidence for:

- intent received
- registry searched
- candidate selected
- card created
- design task created
- proposal submitted
- validation passed or failed
- governance requested
- proposal approved or rejected

Audit payloads should store references and summaries, not large artifact bodies.

## First Sprint Acceptance Criteria

- No agent-specific role, table, endpoint, or API namespace is introduced.
- Intent ingress works through generic `/genesis` endpoints.
- External clients are represented as ordinary participants.
- A participant with Intent Operator permission can submit structured intent and create ingress Cards in scope.
- A participant with Workflow Architect permission can discover workflows and submit proposals in scope.
- Generated proposals run through normal Patch Panel schema and graph validation.
- A proposing participant cannot approve or publish its own proposal unless a separate explicit permission is granted.
- All actions are auditable by participant, permission, scope, and target.

## Later Enhancements

- Free-form conversational intent parsing outside the runtime.
- Semantic registry search.
- Cost and latency-aware workflow recommendation.
- Workflow composition from reusable subworkflows.
- Human-in-the-loop clarifying questions.
- Tool availability and secret-scope negotiation.
- UI review queue for workflow genesis proposals.
