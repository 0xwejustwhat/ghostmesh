from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import Connection

from ghostmesh.domain import (
    ArtifactReference,
    AuthorizationAuditEvent,
    AuthorizationDecision,
    Participant,
    ParticipantType,
    PermissionGrant,
    PermissionName,
    Role,
    RoleAssignment,
    RoleName,
    Scope,
    ScopeType,
)
from ghostmesh.persistence.tables import (
    authorization_audit_events,
    participant_roles,
    participants,
    permission_grants,
    roles,
)


def artifact_ref(card_id: str | UUID, *, role: str = "draft") -> ArtifactReference:
    card_uuid = UUID(str(card_id))
    return ArtifactReference(
        card_id=card_uuid,
        storage_ref=f"git:working-tree:artifacts/{card_uuid}/{role}.txt",
        content_hash="sha256:" + ("a" * 64),
        content_type="text/plain",
        size_bytes=12,
        metadata={"role": role},
    )


def authority_fixture() -> tuple[Participant, Role, RoleAssignment, PermissionGrant]:
    participant = Participant(
        id="participant-fixture-worker",
        type=ParticipantType.SCRIPT,
        display_name="Fixture Worker",
    )
    role = Role(
        id="role-fixture-worker",
        name=RoleName.WORKER,
        permissions=[
            PermissionName.CARD_VIEW,
            PermissionName.CARD_CLAIM,
            PermissionName.CARD_SUBMIT_ARTIFACT,
            PermissionName.CARD_RELEASE,
        ],
    )
    scope = Scope(type=ScopeType.WORKFLOW, id="fixture-workflow")
    assignment = RoleAssignment(
        participant_id=participant.id,
        role_id=role.id,
        scope=scope,
    )
    grant = PermissionGrant(
        role_id=role.id,
        permission=PermissionName.CARD_CLAIM,
        scope=scope,
    )
    return participant, role, assignment, grant


def seed_authority_fixture(connection: Connection) -> tuple[Participant, Role]:
    participant, role, assignment, grant = authority_fixture()
    now = datetime.now(UTC)

    connection.execute(
        participants.insert().values(
            id=participant.id,
            type=participant.type.value,
            display_name=participant.display_name,
            status=participant.status.value,
            trust_level=participant.trust_level,
            auth_method=participant.auth_method,
            participant_metadata=participant.metadata,
            created_at=participant.created_at,
            archived_at=participant.archived_at,
        )
    )
    connection.execute(
        roles.insert().values(
            id=role.id,
            name=str(role.name),
            description=role.description,
            role_metadata=role.metadata,
            created_at=role.created_at,
        )
    )
    connection.execute(
        participant_roles.insert().values(
            id=assignment.id,
            participant_id=assignment.participant_id,
            role_id=assignment.role_id,
            scope_type=assignment.scope.type.value,
            scope_id=assignment.scope.id,
            assigned_by=assignment.assigned_by,
            expires_at=assignment.expires_at,
            created_at=assignment.created_at,
            revoked_at=assignment.revoked_at,
            assignment_metadata=assignment.metadata,
        )
    )
    connection.execute(
        permission_grants.insert().values(
            id=grant.id,
            participant_id=grant.participant_id,
            role_id=grant.role_id,
            permission=grant.permission.value,
            scope_type=grant.scope.type.value,
            scope_id=grant.scope.id,
            granted_by=grant.granted_by,
            expires_at=grant.expires_at,
            created_at=grant.created_at,
            revoked_at=grant.revoked_at,
            grant_metadata=grant.metadata,
        )
    )
    decision = AuthorizationDecision(
        id=uuid4(),
        participant_id=participant.id,
        permission=PermissionName.CARD_CLAIM,
        scope=assignment.scope,
        allowed=True,
        reason="fixture grant",
        evaluated_at=now,
    )
    audit_event = AuthorizationAuditEvent.from_decision(decision, request_ref="fixture-request")
    connection.execute(
        authorization_audit_events.insert().values(
            id=audit_event.id,
            action=audit_event.action.value,
            participant_id=audit_event.participant_id,
            permission=audit_event.permission.value if audit_event.permission else None,
            scope_type=audit_event.scope.type.value if audit_event.scope else None,
            scope_id=audit_event.scope.id if audit_event.scope else None,
            allowed=audit_event.allowed,
            reason=audit_event.reason,
            request_ref=audit_event.request_ref,
            target_ref=audit_event.target_ref,
            event_metadata=audit_event.metadata,
            created_at=audit_event.created_at,
        )
    )
    return participant, role
