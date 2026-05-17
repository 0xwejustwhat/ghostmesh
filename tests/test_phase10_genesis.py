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
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionGrant,
    PermissionName,
    Scope,
    ScopeType,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import InMemoryPatchPanelRegistry, PatchPanelRegistrySearch
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def intent_payload(*, deduplication_key: str = "customer-1:brief") -> dict[str, object]:
    return {
        "requested_by": "intent-operator",
        "deduplication_key": deduplication_key,
        "goal": "review a campaign brief",
        "input_type": "campaign_brief",
        "desired_outputs": ["approved_artifact"],
        "tags": ["campaign"],
        "constraints": {"risk_level": "low", "requires_human_approval": True},
        "launch_if_existing": True,
        "propose_if_missing": True,
    }


def registry_metadata() -> PatchPanelRegistryMetadata:
    return PatchPanelRegistryMetadata(
        name="Campaign Review",
        tags=["campaign"],
        input_types=["campaign_brief"],
        output_types=["approved_artifact"],
        required_tools=["artifact_store"],
        required_permissions=[PermissionName.CARD_CREATE],
        risk_level="low",
        estimated_cost="low",
        estimated_latency="minutes",
        owner_participant_id="intent-operator",
        status=PatchPanelRegistryStatus.PUBLISHED,
    )


def auth_repository() -> InMemoryAuthorizationRepository:
    return InMemoryAuthorizationRepository(
        participants=[
            Participant(id="intent-operator", type=ParticipantType.EXTERNAL_INTEGRATION),
            Participant(id="architect", type=ParticipantType.AGENT),
        ],
        permission_grants=[
            PermissionGrant(
                participant_id="intent-operator",
                permission=PermissionName.PATCH_PANEL_DISCOVER,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="intent-operator",
                permission=PermissionName.CARD_CREATE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
            PermissionGrant(
                participant_id="architect",
                permission=PermissionName.PATCH_PANEL_DISCOVER,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="architect",
                permission=PermissionName.MUTATION_PROPOSE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
        ],
    )


def test_genesis_intent_discovers_and_launches_existing_workflow() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    repository = auth_repository()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    entry = registry.register(
        PatchPanelRegistryEntry.from_patch_panel(patch_panel, registry_metadata())
    )
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            authorization_service=AuthorizationService(repository),
        )
    )

    intent_response = client.post(
        "/genesis/intents",
        json=intent_payload(),
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    )
    launch_response = client.post(
        f"/genesis/intents/{intent_response.json()['id']}/launch",
        json={"registry_entry_id": str(entry.id)},
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    )

    assert intent_response.status_code == 200, intent_response.text
    assert intent_response.json()["candidate_registry_entry_ids"] == [str(entry.id)]
    assert launch_response.status_code == 200, launch_response.text
    assert launch_response.json()["metadata"]["genesis_intent_id"] == intent_response.json()["id"]
    assert repository.audit_events[-1].action == AuditAction.GENESIS_CARD_CREATED


def test_genesis_intent_is_idempotent_by_deduplication_key() -> None:
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            registry=InMemoryPatchPanelRegistry(),
            authorization_service=AuthorizationService(auth_repository()),
        )
    )

    first = client.post(
        "/genesis/intents",
        json=intent_payload(deduplication_key="same-key"),
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    )
    second = client.post(
        "/genesis/intents",
        json=intent_payload(deduplication_key="same-key"),
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]


def test_genesis_proposes_candidate_when_no_existing_workflow_matches() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    repository = auth_repository()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            authorization_service=AuthorizationService(repository),
        )
    )
    intent = client.post(
        "/genesis/intents",
        json=intent_payload(deduplication_key="missing-workflow"),
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    ).json()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    proposal_response = client.post(
        f"/genesis/intents/{intent['id']}/propose",
        json={
            "proposed_by": "architect",
            "candidate_definition": patch_panel.model_dump(mode="json"),
            "registry_metadata": registry_metadata().model_dump(mode="json"),
        },
        headers={"X-Ghostmesh-Participant": "architect"},
    )

    assert intent["status"] == "design_required"
    assert proposal_response.status_code == 200, proposal_response.text
    assert proposal_response.json()["workflow_version"] == "system_pp_approval:1.0.0"
    assert proposal_response.json()["current_bucket"] == "topology_proposals"
    assert proposal_response.json()["payload"]["candidate_definition"]["id"] == "hello_world"
    assert [panel.id for panel in runtime.list_patch_panels()] == ["system_pp_approval"]
    assert [
        entry.patch_panel_id
        for entry in registry.search(PatchPanelRegistrySearch(include_archived=True))
    ] == ["system_pp_approval"]
    assert repository.audit_events[-1].action == AuditAction.GENESIS_PROPOSAL_SUBMITTED


def test_genesis_launch_requires_card_create_scope() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="intent-operator", type=ParticipantType.SCRIPT)],
        permission_grants=[
            PermissionGrant(
                participant_id="intent-operator",
                permission=PermissionName.PATCH_PANEL_DISCOVER,
                scope=Scope.development_global(),
            )
        ],
    )
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    entry = registry.register(
        PatchPanelRegistryEntry.from_patch_panel(patch_panel, registry_metadata())
    )
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            authorization_service=AuthorizationService(repository),
        )
    )

    intent_id = client.post(
        "/genesis/intents",
        json=intent_payload(deduplication_key="no-card-scope"),
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    ).json()["id"]
    response = client.post(
        f"/genesis/intents/{intent_id}/launch",
        json={"registry_entry_id": str(entry.id)},
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "no matching permission grant"}


def test_workflow_genesis_example_patch_panel_is_valid() -> None:
    patch_panel = load_patch_panel(
        Path(__file__).resolve().parents[1]
        / "src"
        / "ghostmesh"
        / "defaults"
        / "patchpanels"
        / "system-pp-approval.yaml"
    )

    assert patch_panel.id == "system_pp_approval"
    assert any(node.id == "topological_validator" for node in patch_panel.nodes)
