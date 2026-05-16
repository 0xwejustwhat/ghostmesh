from __future__ import annotations

from typing import Any

from ghostmesh.auth.repositories import AuthorizationRepository
from ghostmesh.auth.scopes import scope_matches
from ghostmesh.domain import (
    AuditAction,
    AuthorizationAuditEvent,
    AuthorizationDecision,
    ParticipantStatus,
    PermissionName,
    Scope,
)


class AuthorizationService:
    def __init__(self, repository: AuthorizationRepository) -> None:
        self.repository = repository

    def authorize(
        self,
        *,
        participant_id: str,
        permission: PermissionName,
        scope: Scope,
        context: dict[str, Any] | None = None,
    ) -> AuthorizationDecision:
        participant = self.repository.get_participant(participant_id)
        if participant is None:
            return self._record(
                AuthorizationDecision(
                    participant_id=participant_id,
                    permission=permission,
                    scope=scope,
                    allowed=False,
                    reason="participant not found",
                    metadata=context or {},
                )
            )
        if participant.status != ParticipantStatus.ACTIVE:
            return self._record(
                AuthorizationDecision(
                    participant_id=participant_id,
                    permission=permission,
                    scope=scope,
                    allowed=False,
                    reason=f"participant is {participant.status.value}",
                    metadata=context or {},
                )
            )

        grants = self.repository.list_permission_grants(participant_id)
        matched = [
            grant
            for grant in grants
            if grant.permission == permission and scope_matches(grant.scope, scope, context)
        ]
        if matched:
            return self._record(
                AuthorizationDecision(
                    participant_id=participant_id,
                    permission=permission,
                    scope=scope,
                    allowed=True,
                    reason="matched explicit permission grant",
                    matched_grant_ids=[grant.id for grant in matched],
                    metadata=context or {},
                )
            )
        return self._record(
            AuthorizationDecision(
                participant_id=participant_id,
                permission=permission,
                scope=scope,
                allowed=False,
                reason="no matching permission grant",
                metadata=context or {},
            )
        )

    def _record(self, decision: AuthorizationDecision) -> AuthorizationDecision:
        self.repository.record_audit_event(AuthorizationAuditEvent.from_decision(decision))
        return decision

    def record_event(
        self,
        *,
        action: AuditAction,
        participant_id: str | None = None,
        permission: PermissionName | None = None,
        scope: Scope | None = None,
        allowed: bool | None = None,
        reason: str | None = None,
        request_ref: str | None = None,
        target_ref: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuthorizationAuditEvent:
        event = AuthorizationAuditEvent(
            action=action,
            participant_id=participant_id,
            permission=permission,
            scope=scope,
            allowed=allowed,
            reason=reason,
            request_ref=request_ref,
            target_ref=target_ref,
            metadata=metadata or {},
        )
        self.repository.record_audit_event(event)
        return event
