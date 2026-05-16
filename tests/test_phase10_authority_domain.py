from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from ghostmesh.domain import (
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
    legacy_actor_to_participant_id,
)


def test_participants_are_serializable_without_authority_by_type() -> None:
    human = Participant(id="participant-human", type=ParticipantType.HUMAN)
    agent = Participant(id="participant-agent", type=ParticipantType.AGENT)

    assert human.model_dump(mode="json")["type"] == "human"
    assert agent.model_dump(mode="json")["type"] == "agent"
    assert "permissions" not in human.model_dump(mode="json")
    assert "permissions" not in agent.model_dump(mode="json")


def test_scopes_cover_governance_boundaries() -> None:
    assert Scope.global_scope().model_dump(mode="json") == {"type": "global", "id": None}
    assert Scope.development_global().model_dump(mode="json") == {
        "type": "development_global",
        "id": None,
    }

    for scope_type in (
        ScopeType.ORGANIZATION,
        ScopeType.WORKFLOW,
        ScopeType.PATCH_PANEL,
        ScopeType.BUCKET,
        ScopeType.NODE,
        ScopeType.CARD,
        ScopeType.ARTIFACT,
        ScopeType.VERSION,
    ):
        assert Scope(type=scope_type, id=f"{scope_type.value}-1").id is not None


def test_scope_validation_requires_ids_only_for_object_scopes() -> None:
    with pytest.raises(ValidationError):
        Scope(type=ScopeType.WORKFLOW)

    with pytest.raises(ValidationError):
        Scope(type=ScopeType.GLOBAL, id="too-specific")


def test_permission_grants_support_direct_and_role_derived_authority() -> None:
    scope = Scope(type=ScopeType.WORKFLOW, id="workflow-a")
    direct_grant = PermissionGrant(
        participant_id="participant-worker",
        permission=PermissionName.CARD_CLAIM,
        scope=scope,
    )
    role_grant = PermissionGrant(
        role_id="role-worker",
        permission=PermissionName.CARD_SUBMIT_ARTIFACT,
        scope=scope,
    )

    assert direct_grant.is_active()
    assert role_grant.is_active()

    with pytest.raises(ValidationError):
        PermissionGrant(
            participant_id="participant-worker",
            role_id="role-worker",
            permission=PermissionName.CARD_VIEW,
            scope=scope,
        )


def test_role_assignments_can_expire_for_temporary_authority() -> None:
    assignment = RoleAssignment(
        participant_id="participant-worker",
        role_id="role-worker",
        scope=Scope(type=ScopeType.BUCKET, id="draft"),
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    assert assignment.is_active() is False


def test_roles_and_authorization_decisions_are_serializable() -> None:
    role = Role(
        id="role-workflow-architect",
        name=RoleName.WORKFLOW_ARCHITECT,
        permissions=[
            PermissionName.PATCH_PANEL_CREATE,
            PermissionName.MUTATION_PROPOSE,
        ],
    )
    decision = AuthorizationDecision(
        participant_id="participant-architect",
        permission=PermissionName.MUTATION_PROPOSE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="panel-a"),
        allowed=True,
        reason="matched role workflow_architect in patch panel scope",
    )
    audit_event = AuthorizationAuditEvent.from_decision(decision, request_ref="request-1")

    assert role.model_dump(mode="json")["name"] == "workflow_architect"
    assert role.model_dump(mode="json")["permissions"] == [
        "patch_panel:create",
        "mutation:propose",
    ]
    assert decision.model_dump(mode="json")["permission"] == "mutation:propose"
    assert audit_event.action == "authorization:allowed"
    assert audit_event.request_ref == "request-1"


def test_legacy_actor_strings_map_to_stable_participant_ids() -> None:
    participant = Participant.from_legacy_actor("worker-a", participant_type=ParticipantType.SCRIPT)

    assert legacy_actor_to_participant_id("worker-a") == "legacy:worker-a"
    assert participant.id == "legacy:worker-a"
    assert participant.auth_method == "legacy_actor_string"
    assert participant.metadata["legacy_actor_id"] == "worker-a"

    with pytest.raises(ValueError):
        legacy_actor_to_participant_id("   ")
