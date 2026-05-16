from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ghostmesh.domain import (
    AuthorizationAuditEvent,
    Participant,
    ParticipantStatus,
    ParticipantType,
    PermissionGrant,
    PermissionName,
    RoleAssignment,
    Scope,
    ScopeType,
)
from ghostmesh.persistence.tables import (
    authorization_audit_events,
    participant_roles,
    participants,
    permission_grants,
)


class AuthorizationRepository(Protocol):
    def get_participant(self, participant_id: str) -> Participant | None: ...

    def list_participants(self) -> list[Participant]: ...

    def upsert_participant(self, participant: Participant) -> None: ...

    def add_role_assignment(self, assignment: RoleAssignment) -> None: ...

    def add_permission_grant(self, grant: PermissionGrant) -> None: ...

    def list_permission_grants(self, participant_id: str) -> list[PermissionGrant]: ...

    def record_audit_event(self, event: AuthorizationAuditEvent) -> None: ...


class InMemoryAuthorizationRepository:
    def __init__(
        self,
        *,
        participants: list[Participant] | None = None,
        role_assignments: list[RoleAssignment] | None = None,
        permission_grants: list[PermissionGrant] | None = None,
    ) -> None:
        self.participants = {participant.id: participant for participant in participants or []}
        self.role_assignments = list(role_assignments or [])
        self.permission_grants = list(permission_grants or [])
        self.audit_events: list[AuthorizationAuditEvent] = []

    def upsert_participant(self, participant: Participant) -> None:
        self.participants[participant.id] = participant

    def list_participants(self) -> list[Participant]:
        return list(self.participants.values())

    def add_role_assignment(self, assignment: RoleAssignment) -> None:
        self.role_assignments.append(assignment)

    def add_permission_grant(self, grant: PermissionGrant) -> None:
        self.permission_grants.append(grant)

    def get_participant(self, participant_id: str) -> Participant | None:
        return self.participants.get(participant_id)

    def list_permission_grants(self, participant_id: str) -> list[PermissionGrant]:
        now = datetime.now(UTC)
        role_ids = {
            assignment.role_id
            for assignment in self.role_assignments
            if assignment.participant_id == participant_id and assignment.is_active(now)
        }
        return [
            grant
            for grant in self.permission_grants
            if grant.is_active(now)
            and (grant.participant_id == participant_id or grant.role_id in role_ids)
        ]

    def record_audit_event(self, event: AuthorizationAuditEvent) -> None:
        self.audit_events.append(event)


class PostgresAuthorizationRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_participant(self, participant_id: str) -> Participant | None:
        with Session(self.engine) as session:
            row = session.execute(
                select(participants).where(participants.c.id == participant_id)
            ).first()
        if row is None:
            return None
        return _participant_from_row(row._mapping)

    def list_participants(self) -> list[Participant]:
        with Session(self.engine) as session:
            rows = session.execute(select(participants)).all()
        return [_participant_from_row(row._mapping) for row in rows]

    def upsert_participant(self, participant: Participant) -> None:
        values = {
            "id": participant.id,
            "type": participant.type.value,
            "display_name": participant.display_name,
            "status": participant.status.value,
            "trust_level": participant.trust_level,
            "auth_method": participant.auth_method,
            "participant_metadata": participant.metadata,
            "created_at": participant.created_at,
            "archived_at": participant.archived_at,
        }
        with Session(self.engine) as session, session.begin():
            existing = session.execute(
                select(participants.c.id).where(participants.c.id == participant.id)
            ).first()
            if existing:
                session.execute(
                    participants.update()
                    .where(participants.c.id == participant.id)
                    .values(**values)
                )
            else:
                session.execute(participants.insert().values(**values))

    def add_role_assignment(self, assignment: RoleAssignment) -> None:
        from ghostmesh.auth.catalog import get_role_template
        from ghostmesh.persistence.tables import roles

        role_name = assignment.role_id.removeprefix("builtin:")
        template = None
        try:
            from ghostmesh.domain import RoleName

            template = get_role_template(RoleName(role_name))
        except ValueError:
            template = None

        with Session(self.engine) as session, session.begin():
            if template is not None:
                existing_role = session.execute(
                    select(roles.c.id).where(roles.c.id == template.id)
                ).first()
                if existing_role is None:
                    role = template.to_role()
                    session.execute(
                        roles.insert().values(
                            id=role.id,
                            name=str(role.name),
                            description=role.description,
                            role_metadata=role.metadata,
                            created_at=role.created_at,
                        )
                    )
            session.execute(
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

    def add_permission_grant(self, grant: PermissionGrant) -> None:
        with Session(self.engine) as session, session.begin():
            session.execute(
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

    def list_permission_grants(self, participant_id: str) -> list[PermissionGrant]:
        now = datetime.now(UTC)
        with Session(self.engine) as session:
            assignment_rows = session.execute(
                select(participant_roles).where(
                    participant_roles.c.participant_id == participant_id,
                    participant_roles.c.revoked_at.is_(None),
                )
            ).all()
            role_ids = {
                row._mapping["role_id"]
                for row in assignment_rows
                if row._mapping["expires_at"] is None or row._mapping["expires_at"] > now
            }
            grant_rows = session.execute(
                select(permission_grants).where(permission_grants.c.revoked_at.is_(None))
            ).all()

        grants: list[PermissionGrant] = []
        for row in grant_rows:
            grant = _permission_grant_from_row(row._mapping)
            if not grant.is_active(now):
                continue
            if grant.participant_id == participant_id or grant.role_id in role_ids:
                grants.append(grant)
        return grants

    def record_audit_event(self, event: AuthorizationAuditEvent) -> None:
        with Session(self.engine) as session, session.begin():
            session.execute(
                authorization_audit_events.insert().values(
                    id=event.id,
                    action=event.action.value,
                    participant_id=event.participant_id,
                    permission=event.permission.value if event.permission else None,
                    scope_type=event.scope.type.value if event.scope else None,
                    scope_id=event.scope.id if event.scope else None,
                    allowed=event.allowed,
                    reason=event.reason,
                    request_ref=event.request_ref,
                    target_ref=event.target_ref,
                    event_metadata=event.metadata,
                    created_at=event.created_at,
                )
            )


def _participant_from_row(row: object) -> Participant:
    data = dict(row)
    return Participant(
        id=data["id"],
        type=ParticipantType(data["type"]),
        display_name=data["display_name"],
        status=ParticipantStatus(data["status"]),
        trust_level=data["trust_level"],
        auth_method=data["auth_method"],
        metadata=data["participant_metadata"],
        created_at=data["created_at"],
        archived_at=data["archived_at"],
    )


def _permission_grant_from_row(row: object) -> PermissionGrant:
    data = dict(row)
    return PermissionGrant(
        id=data["id"],
        participant_id=data["participant_id"],
        role_id=data["role_id"],
        permission=PermissionName(data["permission"]),
        scope=Scope(type=ScopeType(data["scope_type"]), id=data["scope_id"]),
        granted_by=data["granted_by"],
        expires_at=data["expires_at"],
        created_at=data["created_at"],
        revoked_at=data["revoked_at"],
        metadata=data["grant_metadata"],
    )
