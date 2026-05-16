from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.auth import (
    BUILT_IN_ROLE_TEMPLATES,
    AuthorizationService,
    assign_role_to_participant,
    built_in_roles,
    seed_development_authority,
)
from ghostmesh.config import Settings
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PermissionName,
    RoleName,
    Scope,
    ScopeType,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def permissions_for(role_name: RoleName) -> set[PermissionName]:
    return set(BUILT_IN_ROLE_TEMPLATES[role_name].permissions)


def test_every_builtin_role_template_is_inspectable_data() -> None:
    roles = built_in_roles()

    assert set(BUILT_IN_ROLE_TEMPLATES) == set(RoleName)
    assert {role.name for role in roles} == set(RoleName)
    assert all(role.metadata["builtin"] is True for role in roles)
    assert all(role.permissions for role in roles)
    assert "junction_operator" not in {role.value for role in RoleName}


def test_intent_operator_has_ingress_without_design_authority() -> None:
    permissions = permissions_for(RoleName.INTENT_OPERATOR)

    assert PermissionName.CARD_CREATE in permissions
    assert PermissionName.PATCH_PANEL_DISCOVER in permissions
    assert PermissionName.PATCH_PANEL_CREATE not in permissions
    assert PermissionName.MUTATION_PROPOSE not in permissions
    assert PermissionName.PERMISSION_GRANT not in permissions


def test_routing_validator_uses_validation_submit_permission() -> None:
    permissions = permissions_for(RoleName.ROUTING_VALIDATOR)

    assert PermissionName.CARD_VIEW in permissions
    assert PermissionName.VALIDATION_SUBMIT in permissions
    assert PermissionName.EDGE_CREATE not in permissions


def test_workflow_architect_can_design_and_propose_but_not_promote() -> None:
    permissions = permissions_for(RoleName.WORKFLOW_ARCHITECT)

    assert PermissionName.PATCH_PANEL_CREATE in permissions
    assert PermissionName.PATCH_PANEL_EDIT_DRAFT in permissions
    assert PermissionName.MUTATION_PROPOSE in permissions
    assert PermissionName.SHADOW_CREATE in permissions
    assert PermissionName.MUTATION_PROMOTE not in permissions
    assert PermissionName.PATCH_PANEL_PUBLISH_VERSION not in permissions
    assert PermissionName.SINK_EXECUTE not in permissions
    assert PermissionName.PERMISSION_GRANT not in permissions


def test_shadow_participant_and_observer_defaults_are_conservative() -> None:
    shadow_permissions = permissions_for(RoleName.SHADOW_PARTICIPANT)
    observer_permissions = permissions_for(RoleName.OBSERVER)

    assert PermissionName.MUTATION_PROPOSE in shadow_permissions
    assert PermissionName.SINK_EXECUTE not in shadow_permissions
    assert PermissionName.BOUNDARY_SINK_EGRESS not in shadow_permissions

    assert observer_permissions == {
        PermissionName.CARD_VIEW,
        PermissionName.PATCH_PANEL_DISCOVER,
        PermissionName.AUDIT_VIEW,
    }


def test_admin_receives_all_permissions_as_explicit_role_grants() -> None:
    template = BUILT_IN_ROLE_TEMPLATES[RoleName.ADMIN]
    grants = template.permission_grants(Scope.development_global(), granted_by="seed")

    assert set(template.permissions) == set(PermissionName)
    assert {grant.permission for grant in grants} == set(PermissionName)
    assert all(grant.role_id == template.id for grant in grants)


def test_role_assignment_seed_allows_scoped_authorization() -> None:
    repository = seed_development_authority(participant_id="dev-admin")
    repository.upsert_participant(
        Participant(id="architect", type=ParticipantType.AGENT, display_name="Architect")
    )
    assign_role_to_participant(
        repository,
        participant_id="architect",
        role_name=RoleName.WORKFLOW_ARCHITECT,
        scope=Scope(type=ScopeType.WORKFLOW, id="workflow-a"),
        assigned_by="dev-admin",
    )
    service = AuthorizationService(repository)

    allowed = service.authorize(
        participant_id="architect",
        permission=PermissionName.PATCH_PANEL_CREATE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="panel-a"),
        context={"workflow_id": "workflow-a"},
    )
    denied = service.authorize(
        participant_id="architect",
        permission=PermissionName.MUTATION_PROMOTE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="panel-a"),
        context={"workflow_id": "workflow-a"},
    )

    assert allowed.allowed is True
    assert denied.allowed is False


def test_development_authority_mode_uses_seeded_admin_role() -> None:
    runtime = InMemoryCardRuntime()
    client = TestClient(
        create_app(
            settings=Settings(
                authorization_enabled=True,
                development_authority_enabled=True,
                development_participant_id="local-dev",
            ),
            runtime=runtime,
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    response = client.post(
        "/patchpanels",
        json=patch_panel.model_dump(mode="json"),
        headers={"X-Ghostmesh-Participant": "local-dev"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["id"] == "hello_world"
