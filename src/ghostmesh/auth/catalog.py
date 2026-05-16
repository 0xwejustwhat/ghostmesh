from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from ghostmesh.auth.repositories import InMemoryAuthorizationRepository
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PermissionGrant,
    PermissionName,
    Role,
    RoleAssignment,
    RoleName,
    Scope,
)


class RoleTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: RoleName
    description: str
    permissions: tuple[PermissionName, ...] = Field(default_factory=tuple)
    metadata: dict[str, str] = Field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"builtin:{self.name.value}"

    def to_role(self) -> Role:
        return Role(
            id=self.id,
            name=self.name,
            description=self.description,
            permissions=list(self.permissions),
            metadata={"builtin": True, **self.metadata},
        )

    def permission_grants(
        self,
        scope: Scope,
        *,
        granted_by: str | None = None,
        created_at: datetime | None = None,
    ) -> list[PermissionGrant]:
        grant_time = created_at or datetime.now(UTC)
        return [
            PermissionGrant(
                role_id=self.id,
                permission=permission,
                scope=scope,
                granted_by=granted_by,
                created_at=grant_time,
                metadata={"builtin_role": self.name.value},
            )
            for permission in self.permissions
        ]


BUILT_IN_ROLE_TEMPLATES: dict[RoleName, RoleTemplate] = {
    RoleName.WORKFLOW_OWNER: RoleTemplate(
        name=RoleName.WORKFLOW_OWNER,
        description="Owns workflow design, publishing, mutation promotion, and scoped grants.",
        permissions=(
            PermissionName.PATCH_PANEL_CREATE,
            PermissionName.PATCH_PANEL_EDIT_DRAFT,
            PermissionName.PATCH_PANEL_PUBLISH_VERSION,
            PermissionName.PATCH_PANEL_ARCHIVE,
            PermissionName.PATCH_PANEL_DISCOVER,
            PermissionName.BUCKET_CREATE,
            PermissionName.NODE_CREATE,
            PermissionName.EDGE_CREATE,
            PermissionName.PIPE_BINDING_CREATE,
            PermissionName.MUTATION_VALIDATE,
            PermissionName.MUTATION_PROMOTE,
            PermissionName.SHADOW_CREATE,
            PermissionName.PERMISSION_GRANT,
        ),
    ),
    RoleName.WORKFLOW_DESIGNER: RoleTemplate(
        name=RoleName.WORKFLOW_DESIGNER,
        description="Designs draft workflow topology and proposes mutations.",
        permissions=(
            PermissionName.PATCH_PANEL_CREATE,
            PermissionName.PATCH_PANEL_EDIT_DRAFT,
            PermissionName.PATCH_PANEL_DISCOVER,
            PermissionName.BUCKET_CREATE,
            PermissionName.NODE_CREATE,
            PermissionName.EDGE_CREATE,
            PermissionName.PIPE_BINDING_CREATE,
            PermissionName.MUTATION_PROPOSE,
        ),
    ),
    RoleName.WORKER: RoleTemplate(
        name=RoleName.WORKER,
        description="Claims cards, views work context, submits artifacts, and releases cards.",
        permissions=(
            PermissionName.CARD_VIEW,
            PermissionName.CARD_CLAIM,
            PermissionName.CARD_SUBMIT_ARTIFACT,
            PermissionName.CARD_RELEASE,
        ),
    ),
    RoleName.VALIDATOR: RoleTemplate(
        name=RoleName.VALIDATOR,
        description="Views card context and submits validation decisions.",
        permissions=(PermissionName.CARD_VIEW, PermissionName.VALIDATION_SUBMIT),
    ),
    RoleName.ROUTING_VALIDATOR: RoleTemplate(
        name=RoleName.ROUTING_VALIDATOR,
        description="Reviews routing-sensitive card state and submits validation decisions.",
        permissions=(PermissionName.CARD_VIEW, PermissionName.VALIDATION_SUBMIT),
    ),
    RoleName.SOURCE_OPERATOR: RoleTemplate(
        name=RoleName.SOURCE_OPERATOR,
        description="Admits work through governed source ingress boundaries.",
        permissions=(PermissionName.BOUNDARY_SOURCE_INGRESS, PermissionName.CARD_CREATE),
    ),
    RoleName.SINK_OPERATOR: RoleTemplate(
        name=RoleName.SINK_OPERATOR,
        description="Executes governed sink and egress operations.",
        permissions=(PermissionName.SINK_EXECUTE, PermissionName.BOUNDARY_SINK_EGRESS),
    ),
    RoleName.REVIEWER_APPROVER: RoleTemplate(
        name=RoleName.REVIEWER_APPROVER,
        description="Reviews cards and validates or promotes governed proposals.",
        permissions=(
            PermissionName.CARD_VIEW,
            PermissionName.VALIDATION_SUBMIT,
            PermissionName.MUTATION_VALIDATE,
            PermissionName.MUTATION_PROMOTE,
            PermissionName.PATCH_PANEL_PUBLISH_VERSION,
        ),
    ),
    RoleName.SHADOW_PARTICIPANT: RoleTemplate(
        name=RoleName.SHADOW_PARTICIPANT,
        description="Runs isolated shadow work and proposes improvements.",
        permissions=(
            PermissionName.CARD_VIEW,
            PermissionName.CARD_CLAIM,
            PermissionName.CARD_SUBMIT_ARTIFACT,
            PermissionName.SHADOW_COMPLETE,
            PermissionName.MUTATION_PROPOSE,
        ),
    ),
    RoleName.LEARNING_OPTIMIZER: RoleTemplate(
        name=RoleName.LEARNING_OPTIMIZER,
        description="Observes workflow evidence and proposes optimization mutations.",
        permissions=(
            PermissionName.CARD_VIEW,
            PermissionName.PATCH_PANEL_DISCOVER,
            PermissionName.MUTATION_PROPOSE,
            PermissionName.SHADOW_CREATE,
        ),
    ),
    RoleName.OBSERVER: RoleTemplate(
        name=RoleName.OBSERVER,
        description="Reads workflow context and audit surfaces without mutation authority.",
        permissions=(
            PermissionName.CARD_VIEW,
            PermissionName.PATCH_PANEL_DISCOVER,
            PermissionName.AUDIT_VIEW,
        ),
    ),
    RoleName.ADMIN: RoleTemplate(
        name=RoleName.ADMIN,
        description="Receives every current permission through explicit grants.",
        permissions=tuple(PermissionName),
    ),
    RoleName.INTENT_OPERATOR: RoleTemplate(
        name=RoleName.INTENT_OPERATOR,
        description="Admits structured intent and discovers reusable workflows.",
        permissions=(PermissionName.CARD_CREATE, PermissionName.PATCH_PANEL_DISCOVER),
    ),
    RoleName.WORKFLOW_ARCHITECT: RoleTemplate(
        name=RoleName.WORKFLOW_ARCHITECT,
        description="Designs and proposes workflow topology without production promotion.",
        permissions=(
            PermissionName.PATCH_PANEL_DISCOVER,
            PermissionName.PATCH_PANEL_CREATE,
            PermissionName.PATCH_PANEL_EDIT_DRAFT,
            PermissionName.BUCKET_CREATE,
            PermissionName.NODE_CREATE,
            PermissionName.EDGE_CREATE,
            PermissionName.PIPE_BINDING_CREATE,
            PermissionName.CARD_CREATE,
            PermissionName.MUTATION_PROPOSE,
            PermissionName.SHADOW_CREATE,
        ),
    ),
}


def get_role_template(role_name: RoleName) -> RoleTemplate:
    return BUILT_IN_ROLE_TEMPLATES[role_name]


def built_in_roles() -> list[Role]:
    return [template.to_role() for template in BUILT_IN_ROLE_TEMPLATES.values()]


def seed_development_authority(
    *,
    participant_id: str = "dev-admin",
    scope: Scope | None = None,
) -> InMemoryAuthorizationRepository:
    repository = InMemoryAuthorizationRepository()
    participant = Participant(
        id=participant_id,
        type=ParticipantType.SYSTEM_SERVICE,
        display_name="Development Admin",
        auth_method="development_header",
        metadata={"development_seed": True},
    )
    repository.upsert_participant(participant)
    assign_role_to_participant(
        repository,
        participant_id=participant.id,
        role_name=RoleName.ADMIN,
        scope=scope or Scope.development_global(),
        assigned_by=participant.id,
    )
    return repository


def assign_role_to_participant(
    repository: InMemoryAuthorizationRepository,
    *,
    participant_id: str,
    role_name: RoleName,
    scope: Scope,
    assigned_by: str | None = None,
) -> RoleAssignment:
    template = get_role_template(role_name)
    assignment = RoleAssignment(
        participant_id=participant_id,
        role_id=template.id,
        scope=scope,
        assigned_by=assigned_by,
        metadata={"builtin_role": role_name.value},
    )
    repository.add_role_assignment(assignment)
    for grant in template.permission_grants(scope, granted_by=assigned_by):
        repository.add_permission_grant(grant)
    return assignment
