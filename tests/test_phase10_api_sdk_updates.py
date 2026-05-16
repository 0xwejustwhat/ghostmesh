from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionGrant,
    PermissionName,
    Scope,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import InMemoryPatchPanelRegistry
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def admin_repository() -> InMemoryAuthorizationRepository:
    return InMemoryAuthorizationRepository(
        participants=[Participant(id="admin", type=ParticipantType.HUMAN)],
        permission_grants=[
            PermissionGrant(
                participant_id="admin",
                permission=PermissionName.PARTICIPANT_MANAGE,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="admin",
                permission=PermissionName.PERMISSION_GRANT,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="admin",
                permission=PermissionName.PATCH_PANEL_EDIT_DRAFT,
                scope=Scope.development_global(),
            ),
        ],
    )


def test_dev_participant_management_endpoints_create_assign_grant_and_inspect() -> None:
    repository = admin_repository()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            authorization_service=AuthorizationService(repository),
        )
    )

    created = client.post(
        "/participants",
        json={"id": "worker-participant", "type": "script", "display_name": "Worker"},
        headers={"X-Ghostmesh-Participant": "admin"},
    )
    listed = client.get("/participants", headers={"X-Ghostmesh-Participant": "admin"})
    assigned = client.post(
        "/participants/worker-participant/roles",
        json={"role_name": "worker", "scope": {"type": "workflow", "id": "workflow-a"}},
        headers={"X-Ghostmesh-Participant": "admin"},
    )
    direct_grant = client.post(
        "/participants/worker-participant/permissions",
        json={"permission": "audit:view", "scope": {"type": "global"}},
        headers={"X-Ghostmesh-Participant": "admin"},
    )
    permissions = client.get(
        "/participants/worker-participant/permissions",
        headers={"X-Ghostmesh-Participant": "admin"},
    )

    assert created.status_code == 200, created.text
    assert listed.status_code == 200, listed.text
    assert assigned.status_code == 200, assigned.text
    assert direct_grant.status_code == 200, direct_grant.text
    permission_names = {grant["permission"] for grant in permissions.json()}
    assert "card:claim" in permission_names
    assert "card:submit_artifact" in permission_names
    assert "audit:view" in permission_names
    assert any(participant["id"] == "worker-participant" for participant in listed.json())


def test_draft_registry_metadata_can_be_updated_through_api() -> None:
    repository = admin_repository()
    registry = InMemoryPatchPanelRegistry()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    entry = registry.register(
        PatchPanelRegistryEntry.from_patch_panel(
            patch_panel,
            PatchPanelRegistryMetadata(
                name="Draft Name",
                tags=["old"],
                input_types=["brief"],
                output_types=["artifact"],
                status=PatchPanelRegistryStatus.DRAFT,
            ),
        )
    )
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            registry=registry,
            authorization_service=AuthorizationService(repository),
        )
    )

    response = client.patch(
        f"/registry/patchpanels/{entry.id}",
        json={
            "name": "Updated Draft",
            "tags": ["new"],
            "input_types": ["brief"],
            "output_types": ["approved_artifact"],
            "required_tools": ["artifact_store"],
            "required_permissions": ["card:create"],
            "status": "draft",
        },
        headers={"X-Ghostmesh-Participant": "admin"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Updated Draft"
    assert response.json()["tags"] == ["new"]
