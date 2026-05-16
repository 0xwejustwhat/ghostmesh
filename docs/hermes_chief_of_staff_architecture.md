# Hermes Chief-of-Staff Architecture

## Purpose

Hermes is the conversational workflow-design pattern for Ghost Mesh. It turns user intent into Cards, Patch Panel discovery, and governed workflow proposals while remaining inside the same participant, permission, validation, and audit model as every other actor.

Hermes is not a hidden orchestrator. Hermes is a participant.

## Core Principle

```text
Hermes designs and proposes.
Patch Panels govern.
Validators judge.
The runtime enforces.
Reviewers promote.
```

## What Hermes May Do

Depending on scoped permissions, Hermes may:

- discover Patch Panels
- create Cards
- create Patch Panel drafts
- create buckets, nodes, edges, and pipe bindings in proposals
- define acceptance contracts
- propose workflow mutations
- launch shadow lanes
- request governance approval
- instantiate subworkflow Cards

## What Hermes Must Not Do By Default

Hermes should not:

- bypass Patch Panel validation
- embed Patch Panels inside worker behavior
- self-escalate permissions
- approve its own production mutations
- publish workflows directly
- execute production sinks unless separately granted sink authority
- route Cards outside declared Patch Panel edges

## MVP Request Shape

The first Hermes sprint should avoid free-form LLM dependency. It should accept structured intent so the Ghost Mesh mechanics can be proven first.

Suggested request:

```yaml
intent:
  requested_by: participant_id
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

## Flow A: Existing Workflow Found

```text
structured intent
-> authorize Hermes for patch_panel:discover
-> search Patch Panel registry
-> select published candidate
-> authorize Hermes for card:create in workflow scope
-> create Card in source bucket
-> emit audit events
```

Hermes does not need graph-wide authority. It only needs discovery and card creation in the relevant scope.

## Flow B: No Suitable Workflow Found

```text
structured intent
-> authorize Hermes for patch_panel:discover
-> no suitable registry match
-> authorize Hermes for mutation:propose and patch_panel:create
-> generate candidate Patch Panel definition
-> run schema and graph validation
-> store proposal and validation report
-> request governance review
```

The proposed workflow is not production until a separate participant approves or promotes it.

## Flow C: Workflow Improvement Detected

```text
observability evidence
-> Learning or Hermes participant proposes mutation
-> shadow lane auditions change
-> mutation validator records evidence
-> reviewer approves promotion
-> registry supersedes old version
```

This preserves the Ghost Mesh principle that every improvement must audition.

## Hermes As A Worker Node

A Hermes Worker Node can exist in a Patch Panel like any other worker:

```yaml
nodes:
  - id: hermes_designer
    type: worker
    input_pipes:
      - intent_input
    output_pipes:
      - proposal_output
    config:
      participant_id: hermes
      mode: workflow_design
```

The node receives bounded input and submits artifact references or typed proposal payloads. The Patch Panel, not the worker, decides where the output goes next.

## Example Genesis Patch Panel

Suggested minimal topology:

```text
Intent Source
-> Hermes Workflow Designer
-> Patch Panel Validator
-> Governance Reviewer
-> Registry Publication Sink
```

Possible buckets:

- `intent_inbox`
- `candidate_workflow_drafts`
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
POST /hermes/intents
GET /hermes/intents/{intent_id}
POST /hermes/intents/{intent_id}/launch
POST /hermes/intents/{intent_id}/propose
```

These can be thin service endpoints over existing runtime, registry, proposal, and authorization services. They should not become a second orchestration system.

## Audit Events

Hermes should emit audit evidence for:

- intent received
- registry searched
- candidate selected
- card created
- proposal generated
- validation passed or failed
- governance requested
- proposal approved or rejected

Audit payloads should store references and summaries, not large artifact bodies.

## Permission Profile

Recommended default Hermes role:

- `patch_panel:discover`
- `card:create`
- `patch_panel:create`
- `patch_panel:edit_draft`
- `bucket:create`
- `node:create`
- `edge:create`
- `pipe_binding:create`
- `mutation:propose`
- `shadow:create`

Not included by default:

- `mutation:promote`
- `patch_panel:publish_version`
- `sink:execute`
- `permission:grant`

## First Sprint Acceptance Criteria

- Hermes exists as a participant with a scoped role.
- Hermes can search the Patch Panel registry.
- Hermes can create Cards for an existing published workflow when authorized.
- Hermes can create a Patch Panel proposal when no match exists.
- Hermes-generated proposals run through normal Patch Panel schema and graph validation.
- Hermes cannot approve or publish its own proposal unless a separate explicit permission is granted.
- All Hermes actions are auditable.

## Later Enhancements

- Free-form conversational intent parsing.
- Semantic registry search.
- Cost and latency-aware workflow recommendation.
- Workflow composition from reusable subworkflows.
- Human-in-the-loop clarifying questions.
- Tool availability and secret-scope negotiation.
- UI review queue for Hermes proposals.
