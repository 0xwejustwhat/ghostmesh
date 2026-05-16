from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import (
    AuditAction,
    Participant,
    ParticipantType,
    PatchPanel,
    PatchPanelProposalStatus,
    PatchPanelProposalType,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionGrant,
    PermissionName,
    Scope,
    ScopeType,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import (
    InMemoryPatchPanelProposalStore,
    InMemoryPatchPanelRegistry,
    PatchPanelRegistrySearch,
)
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def proposal_metadata() -> PatchPanelRegistryMetadata:
    return PatchPanelRegistryMetadata(
        name="Generated Hello",
        description="Generated workflow candidate",
        tags=["generated"],
        input_types=["brief"],
        output_types=["approved_artifact"],
        required_tools=["artifact_store"],
        required_permissions=[PermissionName.CARD_CREATE],
        risk_level="low",
        estimated_cost="low",
        estimated_latency="minutes",
        owner_participant_id="architect",
        status=PatchPanelRegistryStatus.REVIEW,
    )


def proposal_payload(patch_panel: PatchPanel) -> dict[str, object]:
    return {
        "proposal_type": PatchPanelProposalType.CREATE.value,
        "proposed_by": "architect",
        "candidate_definition": patch_panel.model_dump(mode="json"),
        "registry_metadata": proposal_metadata().model_dump(mode="json"),
    }


def auth_repository() -> InMemoryAuthorizationRepository:
    return InMemoryAuthorizationRepository(
        participants=[
            Participant(id="architect", type=ParticipantType.AGENT),
            Participant(id="reviewer", type=ParticipantType.HUMAN),
        ],
        permission_grants=[
            PermissionGrant(
                participant_id="architect",
                permission=PermissionName.MUTATION_PROPOSE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
            PermissionGrant(
                participant_id="architect",
                permission=PermissionName.PATCH_PANEL_DISCOVER,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="reviewer",
                permission=PermissionName.MUTATION_VALIDATE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
            PermissionGrant(
                participant_id="reviewer",
                permission=PermissionName.MUTATION_PROMOTE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
            PermissionGrant(
                participant_id="reviewer",
                permission=PermissionName.PATCH_PANEL_PUBLISH_VERSION,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
            PermissionGrant(
                participant_id="reviewer",
                permission=PermissionName.PATCH_PANEL_DISCOVER,
                scope=Scope.development_global(),
            ),
        ],
    )


def test_valid_proposal_enters_review_without_registering_runtime_workflow() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    proposal_store = InMemoryPatchPanelProposalStore()
    repository = auth_repository()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            proposal_store=proposal_store,
            authorization_service=AuthorizationService(repository),
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    response = client.post(
        "/registry/patchpanels/proposals",
        json=proposal_payload(patch_panel),
        headers={"X-Ghostmesh-Participant": "architect"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == PatchPanelProposalStatus.IN_REVIEW.value
    assert response.json()["validation_report"]["valid"] is True
    assert runtime.list_patch_panels() == []
    assert registry.search(PatchPanelRegistrySearch()) == []
    assert repository.audit_events[-1].action == AuditAction.PATCH_PANEL_PROPOSAL_SUBMITTED


def test_invalid_generated_patch_panel_fails_before_review() -> None:
    runtime = InMemoryCardRuntime()
    proposal_store = InMemoryPatchPanelProposalStore()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            proposal_store=proposal_store,
            authorization_service=AuthorizationService(auth_repository()),
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    invalid_patch_panel = patch_panel.model_copy(
        update={
            "pipe_bindings": {
                key: value
                for key, value in patch_panel.pipe_bindings.items()
                if key != "worker_input"
            }
        }
    )

    response = client.post(
        "/registry/patchpanels/proposals",
        json=proposal_payload(invalid_patch_panel),
        headers={"X-Ghostmesh-Participant": "architect"},
    )

    assert response.status_code == 422
    assert "validation failed" in response.json()["detail"]
    assert proposal_store.proposals == {}


def test_approval_is_separate_permissioned_action_and_publishes_registry_entry() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    proposal_store = InMemoryPatchPanelProposalStore()
    repository = auth_repository()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            proposal_store=proposal_store,
            authorization_service=AuthorizationService(repository),
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    create_response = client.post(
        "/registry/patchpanels/proposals",
        json=proposal_payload(patch_panel),
        headers={"X-Ghostmesh-Participant": "architect"},
    )
    proposal_id = create_response.json()["id"]

    denied_response = client.post(
        f"/registry/patchpanels/proposals/{proposal_id}/approve",
        json={"reason": "self approval should not pass"},
        headers={"X-Ghostmesh-Participant": "architect"},
    )
    approved_response = client.post(
        f"/registry/patchpanels/proposals/{proposal_id}/approve",
        json={"reason": "valid generated workflow"},
        headers={"X-Ghostmesh-Participant": "reviewer"},
    )

    assert denied_response.status_code == 403
    assert approved_response.status_code == 200, approved_response.text
    approved = approved_response.json()
    assert approved["status"] == PatchPanelProposalStatus.PROMOTED.value
    assert [event["action"] for event in approved["review_events"]] == ["submitted", "approved"]
    assert runtime.list_patch_panels()[0].id == "hello_world"
    published_entries = registry.search(PatchPanelRegistrySearch())
    assert published_entries[0].status == PatchPanelRegistryStatus.PUBLISHED
    assert repository.audit_events[-1].action == AuditAction.PATCH_PANEL_PROPOSAL_APPROVED


def test_rejection_keeps_append_only_review_history_and_does_not_publish() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    proposal_store = InMemoryPatchPanelProposalStore()
    repository = auth_repository()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            proposal_store=proposal_store,
            authorization_service=AuthorizationService(repository),
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    proposal_id = client.post(
        "/registry/patchpanels/proposals",
        json=proposal_payload(patch_panel),
        headers={"X-Ghostmesh-Participant": "architect"},
    ).json()["id"]

    rejected_response = client.post(
        f"/registry/patchpanels/proposals/{proposal_id}/reject",
        json={"reason": "needs clearer owner"},
        headers={"X-Ghostmesh-Participant": "reviewer"},
    )

    assert rejected_response.status_code == 200, rejected_response.text
    rejected = rejected_response.json()
    assert rejected["status"] == PatchPanelProposalStatus.REJECTED.value
    assert [event["action"] for event in rejected["review_events"]] == ["submitted", "rejected"]
    assert rejected["review_events"][1]["reason"] == "needs clearer owner"
    assert runtime.list_patch_panels() == []
    assert registry.search(PatchPanelRegistrySearch()) == []
