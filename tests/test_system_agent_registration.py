from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PermissionName,
    RoleAssignment,
    RoleName,
    Scope,
)
from ghostmesh.nodes import NodeExecutor, ValidatorExecutionInput
from ghostmesh.patchpanel import PatchPanelValidator, load_patch_panel
from ghostmesh.registry import InMemoryPatchPanelRegistry
from ghostmesh.runtime import InMemoryCardRuntime
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError

ROOT = Path(__file__).resolve().parents[1]
SYSTEM_AGENT_REGISTRATION = (
    ROOT / "src" / "ghostmesh" / "defaults" / "patchpanels" / "system-agent-registration.yaml"
)


def onboarding_payload(participant_id: str = "agent-1") -> dict[str, object]:
    return {
        "participant": Participant(
            id=participant_id,
            type=ParticipantType.AGENT,
            display_name="Agent One",
            auth_method="mcp_local",
        ).model_dump(mode="json"),
        "role_assignments": [
            {
                "role_name": RoleName.WORKER.value,
                "scope": Scope.global_scope().model_dump(mode="json"),
                "assigned_by": "root-operator",
            }
        ],
    }


def test_system_agent_registration_patch_panel_validates() -> None:
    patch_panel = load_patch_panel(SYSTEM_AGENT_REGISTRATION)

    report = PatchPanelValidator().validate(patch_panel)

    assert patch_panel.id == "system_agent_registration"
    assert report.node_count == 4


def test_registration_compliance_validator_routes_payloads() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    create_app(settings=Settings(), runtime=runtime, registry=registry)
    patch_panel = load_patch_panel(SYSTEM_AGENT_REGISTRATION)
    executor = NodeExecutor(patch_panel=patch_panel, runtime=runtime, registry=registry)
    valid_card = runtime.create_card(
        patch_panel_id="system_agent_registration",
        payload=onboarding_payload(),
    )
    invalid_card = runtime.create_card(
        patch_panel_id="system_agent_registration",
        payload={"participant": {"id": "missing-type"}},
    )

    valid = executor.execute_validator(
        ValidatorExecutionInput(
            card_id=valid_card.id,
            validator_id="registration_compliance_validator",
        )
    )
    invalid = executor.execute_validator(
        ValidatorExecutionInput(
            card_id=invalid_card.id,
            validator_id="registration_compliance_validator",
        )
    )

    assert valid.payload["accepted"] is True
    assert valid.payload["output_pipe"] == "registration_compliant"
    assert runtime.get_card(valid_card.id).current_bucket == "registration_admin_review"
    assert invalid.payload["accepted"] is False
    assert invalid.payload["output_pipe"] == "registration_noncompliant"
    assert runtime.get_card(invalid_card.id).current_bucket == "registration_rejected"


def test_authority_provisioner_sink_creates_participant_and_roles() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    repository = InMemoryAuthorizationRepository()
    create_app(
        settings=Settings(),
        runtime=runtime,
        registry=registry,
        authorization_service=AuthorizationService(repository),
    )
    patch_panel = load_patch_panel(SYSTEM_AGENT_REGISTRATION)
    executor = NodeExecutor(
        patch_panel=patch_panel,
        runtime=runtime,
        registry=registry,
        authorization_repository=repository,
    )
    card = runtime.create_card(
        patch_panel_id="system_agent_registration",
        payload=onboarding_payload("agent-provisioned"),
    )
    executor.execute_validator(
        ValidatorExecutionInput(card_id=card.id, validator_id="registration_compliance_validator")
    )
    executor.execute_validator(
        ValidatorExecutionInput(
            card_id=card.id,
            validator_id="registration_admin_reviewer",
            selected_exit="registration_approved",
            reason="approved by root operator",
        )
    )

    result = executor.execute_sink(card_id=card.id, sink_id="authority_provisioner_sink")
    executor.execute_sink(card_id=card.id, sink_id="authority_provisioner_sink")

    assert result.external_reference == "agent-provisioned"
    assert repository.get_participant("agent-provisioned") is not None
    assert [
        assignment.role_id for assignment in repository.list_role_assignments("agent-provisioned")
    ] == [f"builtin:{RoleName.WORKER.value}"]
    grants = repository.list_permission_grants("agent-provisioned")
    assert {grant.permission for grant in grants} >= {
        PermissionName.CARD_CLAIM,
        PermissionName.CARD_SUBMIT_ARTIFACT,
    }
    assert len(grants) == len({grant.permission for grant in grants})


def test_authority_provisioner_sink_requires_approval_history() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    repository = InMemoryAuthorizationRepository()
    create_app(
        settings=Settings(),
        runtime=runtime,
        registry=registry,
        authorization_service=AuthorizationService(repository),
    )
    patch_panel = load_patch_panel(SYSTEM_AGENT_REGISTRATION)
    executor = NodeExecutor(
        patch_panel=patch_panel,
        runtime=runtime,
        registry=registry,
        authorization_repository=repository,
    )
    card = runtime.create_card(
        patch_panel_id="system_agent_registration",
        payload=onboarding_payload("agent-blocked"),
    )
    runtime.move_card(card_id=card.id, to_bucket="authority_provisioning")

    with pytest.raises(ConflictError, match="compliance validation and admin approval"):
        executor.execute_sink(card_id=card.id, sink_id="authority_provisioner_sink")


def test_authority_provisioner_sink_requires_authorization_repository() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    create_app(settings=Settings(), runtime=runtime, registry=registry)
    patch_panel = load_patch_panel(SYSTEM_AGENT_REGISTRATION)
    executor = NodeExecutor(patch_panel=patch_panel, runtime=runtime, registry=registry)
    card = runtime.create_card(
        patch_panel_id="system_agent_registration",
        payload=onboarding_payload("agent-no-repository"),
    )
    executor.execute_validator(
        ValidatorExecutionInput(card_id=card.id, validator_id="registration_compliance_validator")
    )
    executor.execute_validator(
        ValidatorExecutionInput(
            card_id=card.id,
            validator_id="registration_admin_reviewer",
            selected_exit="registration_approved",
        )
    )

    with pytest.raises(InvalidOperationError, match="Authorization repository unavailable"):
        executor.execute_sink(card_id=card.id, sink_id="authority_provisioner_sink")


def test_role_assignment_listing_ignores_expired_and_revoked_roles() -> None:
    now = datetime.now(UTC)
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="agent-expired", type=ParticipantType.AGENT)],
        role_assignments=[
            RoleAssignment(
                participant_id="agent-expired",
                role_id=f"builtin:{RoleName.WORKER.value}",
                scope=Scope.global_scope(),
                expires_at=now - timedelta(minutes=1),
            ),
            RoleAssignment(
                participant_id="agent-expired",
                role_id=f"builtin:{RoleName.VALIDATOR.value}",
                scope=Scope.global_scope(),
                revoked_at=now,
            ),
            RoleAssignment(
                participant_id="agent-expired",
                role_id=f"builtin:{RoleName.OBSERVER.value}",
                scope=Scope.global_scope(),
            ),
        ],
    )

    assert [
        assignment.role_id for assignment in repository.list_role_assignments("agent-expired")
    ] == [f"builtin:{RoleName.OBSERVER.value}"]
