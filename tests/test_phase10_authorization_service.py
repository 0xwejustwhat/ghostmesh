from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PermissionGrant,
    PermissionName,
    RoleAssignment,
    Scope,
    ScopeType,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_authorization_service_allows_non_human_with_correct_scope() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="agent-designer", type=ParticipantType.AGENT)],
        permission_grants=[
            PermissionGrant(
                participant_id="agent-designer",
                permission=PermissionName.PATCH_PANEL_CREATE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            )
        ],
    )
    service = AuthorizationService(repository)

    decision = service.authorize(
        participant_id="agent-designer",
        permission=PermissionName.PATCH_PANEL_CREATE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
    )

    assert decision.allowed is True
    assert repository.audit_events[0].allowed is True


def test_authorization_service_denies_same_role_wrong_scope() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="worker", type=ParticipantType.SCRIPT)],
        role_assignments=[
            RoleAssignment(
                participant_id="worker",
                role_id="role-worker",
                scope=Scope(type=ScopeType.WORKFLOW, id="workflow-a"),
            )
        ],
        permission_grants=[
            PermissionGrant(
                role_id="role-worker",
                permission=PermissionName.CARD_CLAIM,
                scope=Scope(type=ScopeType.WORKFLOW, id="workflow-a"),
            )
        ],
    )
    service = AuthorizationService(repository)

    decision = service.authorize(
        participant_id="worker",
        permission=PermissionName.CARD_CLAIM,
        scope=Scope(type=ScopeType.BUCKET, id="bucket-b"),
        context={"workflow_id": "workflow-b"},
    )

    assert decision.allowed is False
    assert decision.reason == "no matching permission grant"
    assert repository.audit_events[0].allowed is False


def test_protected_api_denies_missing_participant_with_consistent_403() -> None:
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            authorization_service=AuthorizationService(InMemoryAuthorizationRepository()),
        )
    )

    response = client.post(
        "/cards",
        json={"patch_panel_id": "hello_world", "payload": {"title": "blocked"}},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "missing Ghost Mesh participant"}


def test_protected_api_allows_authorized_external_integration() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[
            Participant(
                id="integration-designer",
                type=ParticipantType.EXTERNAL_INTEGRATION,
            )
        ],
        permission_grants=[
            PermissionGrant(
                participant_id="integration-designer",
                permission=PermissionName.PATCH_PANEL_CREATE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            )
        ],
    )
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            authorization_service=AuthorizationService(repository),
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    response = client.post(
        "/patchpanels",
        json=patch_panel.model_dump(mode="json"),
        headers={"X-Ghostmesh-Participant": "integration-designer"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == "hello_world"
    assert repository.audit_events[0].allowed is True
