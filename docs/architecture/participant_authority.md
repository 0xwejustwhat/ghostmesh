# Participant Authority Architecture

Participant type affects interface. Permissions affect authority.

Humans, agents, scripts, services, vendors, organizations, integrations, and
subworkflows are participants. None receive implicit authority because of what they
are. Sensitive actions are authorized through explicit permissions and scopes.

Important permissions include:

- `card:create`, `card:claim`, `card:submit_artifact`
- `validation:submit`
- `mutation:propose`, `mutation:validate`, `mutation:promote`
- `patch_panel:discover`, `patch_panel:create`, `patch_panel:publish_version`
- `sink:execute`

Governance reviewers may be humans or agents. The runtime treats them identically and
checks only participant identity, permission, scope, and policy context.

## Root Bootstrap

Every application entry point uses the shared system initializer. It loads system
Patch Panels and seeds a root operator participant before REST or MCP mutations run.
The root id comes from `GHOSTMESH_ROOT_PARTICIPANT_ID` and defaults to
`root-operator`. The initializer assigns the built-in `admin` role on global scope
idempotently, ignoring expired or revoked assignments when deciding whether a fresh
assignment is needed.

## Native Participant Expansion

New participants are onboarded through the `system_agent_registration` Patch Panel.
The workflow is participant-neutral: a human, agent, script, or service can submit or
review only when its participant record has the required permissions.

Cards enter `registration_compliance` from `registration_source`. The automated
`registration_compliance_validator` checks that the payload contains:

- `participant`: a valid `Participant` object.
- `role_assignments`: one or more role requests with `role_name`, `scope`, and
  optional `assigned_by`.

Compliant cards exit through `registration_compliant` into
`registration_admin_review`. Invalid cards exit through `registration_noncompliant`
into `registration_rejected`. The `registration_admin_reviewer` then chooses
`registration_approved` or `registration_rejected` using normal validator execution.

Approved cards move to `authority_provisioning`. The `authority_provisioner_sink`
requires both compliance validation and admin approval history before it writes. Its
egress action calls the active `AuthorizationRepository` to upsert the participant,
add active role assignments, and seed the built-in role permission grants without
duplicating active grants.
