from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ParticipantType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    SCRIPT = "script"
    SERVICE = "service"
    SYSTEM_SERVICE = "system_service"
    VENDOR = "vendor"
    ORGANIZATION = "organization"
    EXTERNAL_INTEGRATION = "external_integration"
    SUBWORKFLOW = "subworkflow"


class ParticipantStatus(StrEnum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    ARCHIVED = "archived"


class RoleName(StrEnum):
    WORKFLOW_OWNER = "workflow_owner"
    WORKFLOW_DESIGNER = "workflow_designer"
    WORKER = "worker"
    VALIDATOR = "validator"
    ROUTING_VALIDATOR = "routing_validator"
    SOURCE_OPERATOR = "source_operator"
    SINK_OPERATOR = "sink_operator"
    REVIEWER_APPROVER = "reviewer_approver"
    SHADOW_PARTICIPANT = "shadow_participant"
    LEARNING_OPTIMIZER = "learning_optimizer"
    OBSERVER = "observer"
    ADMIN = "admin"
    INTENT_OPERATOR = "intent_operator"
    WORKFLOW_ARCHITECT = "workflow_architect"


class PermissionName(StrEnum):
    PATCH_PANEL_CREATE = "patch_panel:create"
    PATCH_PANEL_EDIT_DRAFT = "patch_panel:edit_draft"
    PATCH_PANEL_PUBLISH_VERSION = "patch_panel:publish_version"
    PATCH_PANEL_ARCHIVE = "patch_panel:archive"
    PATCH_PANEL_DISCOVER = "patch_panel:discover"
    BUCKET_CREATE = "bucket:create"
    NODE_CREATE = "node:create"
    EDGE_CREATE = "edge:create"
    PIPE_BINDING_CREATE = "pipe_binding:create"
    CARD_CREATE = "card:create"
    CARD_CLAIM = "card:claim"
    CARD_SUBMIT_ARTIFACT = "card:submit_artifact"
    CARD_RELEASE = "card:release"
    CARD_VIEW = "card:view"
    VALIDATION_SUBMIT = "validation:submit"
    MUTATION_PROPOSE = "mutation:propose"
    MUTATION_VALIDATE = "mutation:validate"
    MUTATION_PROMOTE = "mutation:promote"
    SHADOW_CREATE = "shadow:create"
    SHADOW_COMPLETE = "shadow:complete"
    SINK_EXECUTE = "sink:execute"
    BOUNDARY_SOURCE_INGRESS = "boundary:source_ingress"
    BOUNDARY_SINK_EGRESS = "boundary:sink_egress"
    PARTICIPANT_MANAGE = "participant:manage"
    PERMISSION_GRANT = "permission:grant"
    AUDIT_VIEW = "audit:view"


class ScopeType(StrEnum):
    GLOBAL = "global"
    DEVELOPMENT_GLOBAL = "development_global"
    ORGANIZATION = "organization"
    WORKFLOW = "workflow"
    PATCH_PANEL = "patch_panel"
    BUCKET = "bucket"
    NODE = "node"
    CARD = "card"
    ARTIFACT = "artifact"
    VERSION = "version"


class AuditAction(StrEnum):
    AUTHORIZATION_ALLOWED = "authorization:allowed"
    AUTHORIZATION_DENIED = "authorization:denied"
    PATCH_PANEL_PROPOSAL_SUBMITTED = "patch_panel_proposal:submitted"
    PATCH_PANEL_PROPOSAL_APPROVED = "patch_panel_proposal:approved"
    PATCH_PANEL_PROPOSAL_REJECTED = "patch_panel_proposal:rejected"
    GENESIS_INTENT_RECEIVED = "genesis:intent_received"
    GENESIS_REGISTRY_SEARCHED = "genesis:registry_searched"
    GENESIS_CANDIDATE_SELECTED = "genesis:candidate_selected"
    GENESIS_CARD_CREATED = "genesis:card_created"
    GENESIS_PROPOSAL_SUBMITTED = "genesis:proposal_submitted"
    GENESIS_DESIGN_REQUIRED = "genesis:design_required"
    PARTICIPANT_CREATED = "participant:created"
    PARTICIPANT_UPDATED = "participant:updated"
    PARTICIPANT_SUSPENDED = "participant:suspended"
    PARTICIPANT_ARCHIVED = "participant:archived"
    ROLE_ASSIGNED = "role:assigned"
    ROLE_REVOKED = "role:revoked"
    PERMISSION_GRANTED = "permission:granted"
    PERMISSION_REVOKED = "permission:revoked"


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: ScopeType
    id: str | None = None

    @classmethod
    def global_scope(cls) -> Scope:
        return cls(type=ScopeType.GLOBAL)

    @classmethod
    def development_global(cls) -> Scope:
        return cls(type=ScopeType.DEVELOPMENT_GLOBAL)

    @model_validator(mode="after")
    def validate_scope_id(self) -> Scope:
        if self.type in {ScopeType.GLOBAL, ScopeType.DEVELOPMENT_GLOBAL}:
            if self.id is not None:
                raise ValueError(f"{self.type.value} scope must not include an id")
        elif not self.id:
            raise ValueError(f"{self.type.value} scope requires an id")
        return self


class Participant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: ParticipantType
    display_name: str | None = None
    status: ParticipantStatus = ParticipantStatus.ACTIVE
    trust_level: str | None = None
    auth_method: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    archived_at: datetime | None = None

    @classmethod
    def from_legacy_actor(
        cls,
        actor_id: str,
        *,
        participant_type: ParticipantType = ParticipantType.SERVICE,
    ) -> Participant:
        return cls(
            id=legacy_actor_to_participant_id(actor_id),
            type=participant_type,
            display_name=actor_id,
            auth_method="legacy_actor_string",
            metadata={"legacy_actor_id": actor_id},
        )


class Role(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: RoleName | str
    description: str | None = None
    permissions: list[PermissionName] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RoleAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    participant_id: str
    role_id: str
    scope: Scope
    assigned_by: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def is_active(self, at: datetime | None = None) -> bool:
        checked_at = at or datetime.now(UTC)
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > checked_at)


class PermissionGrant(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    permission: PermissionName
    scope: Scope
    participant_id: str | None = None
    role_id: str | None = None
    granted_by: str | None = None
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    revoked_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_grant_target(self) -> PermissionGrant:
        targets = [self.participant_id is not None, self.role_id is not None]
        if targets.count(True) != 1:
            raise ValueError("permission grant must target exactly one participant_id or role_id")
        return self

    def is_active(self, at: datetime | None = None) -> bool:
        checked_at = at or datetime.now(UTC)
        return self.revoked_at is None and (self.expires_at is None or self.expires_at > checked_at)


class AuthorizationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    participant_id: str
    permission: PermissionName
    scope: Scope
    allowed: bool
    reason: str
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    matched_grant_ids: list[UUID] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def audit_action(self) -> AuditAction:
        if self.allowed:
            return AuditAction.AUTHORIZATION_ALLOWED
        return AuditAction.AUTHORIZATION_DENIED


class AuthorizationAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    action: AuditAction
    participant_id: str | None = None
    permission: PermissionName | None = None
    scope: Scope | None = None
    allowed: bool | None = None
    reason: str | None = None
    request_ref: str | None = None
    target_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_decision(
        cls,
        decision: AuthorizationDecision,
        *,
        request_ref: str | None = None,
        target_ref: str | None = None,
    ) -> AuthorizationAuditEvent:
        return cls(
            action=decision.audit_action,
            participant_id=decision.participant_id,
            permission=decision.permission,
            scope=decision.scope,
            allowed=decision.allowed,
            reason=decision.reason,
            request_ref=request_ref,
            target_ref=target_ref,
            metadata=decision.metadata,
        )


def legacy_actor_to_participant_id(actor_id: str) -> str:
    normalized = actor_id.strip()
    if not normalized:
        raise ValueError("actor_id must not be empty")
    return f"legacy:{normalized}"
