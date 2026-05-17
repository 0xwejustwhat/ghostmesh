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
