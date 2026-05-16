from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.auth import (
    AuthorizationService,
    InMemoryAuthorizationRepository,
    assign_role_to_participant,
)
from ghostmesh.config import Settings
from ghostmesh.domain import (
    AuditAction,
    Participant,
    ParticipantStatus,
    ParticipantType,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionGrant,
    PermissionName,
    RoleName,
    Scope,
    ScopeType,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import InMemoryPatchPanelProposalStore, InMemoryPatchPanelRegistry
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_authorization_denies_wrong_permission_suspended_and_missing_participant() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[
            Participant(id="viewer", type=ParticipantType.HUMAN),
            Participant(
                id="suspended",
                type=ParticipantType.SERVICE,
                status=ParticipantStatus.SUSPENDED,
            ),
        ],
        permission_grants=[
            PermissionGrant(
                participant_id="viewer",
                permission=PermissionName.CARD_VIEW,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="suspended",
                permission=PermissionName.CARD_CREATE,
                scope=Scope.development_global(),
            ),
        ],
    )
    service = AuthorizationService(repository)

    wrong_permission = service.authorize(
        participant_id="viewer",
        permission=PermissionName.CARD_CREATE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
    )
    suspended = service.authorize(
        participant_id="suspended",
        permission=PermissionName.CARD_CREATE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
    )
    missing = service.authorize(
        participant_id="missing",
        permission=PermissionName.CARD_CREATE,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
    )

    assert wrong_permission.allowed is False
    assert wrong_permission.reason == "no matching permission grant"
    assert suspended.allowed is False
    assert suspended.reason == "participant is suspended"
    assert missing.allowed is False
    assert missing.reason == "participant not found"
    assert [event.allowed for event in repository.audit_events] == [False, False, False]


def test_workflow_architect_can_discover_and_propose_but_not_self_promote() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    proposal_store = InMemoryPatchPanelProposalStore()
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="architect", type=ParticipantType.AGENT)]
    )
    repository.upsert_participant(Participant(id="admin", type=ParticipantType.HUMAN))
    assign_role_to_participant(
        repository,
        participant_id="architect",
        role_name=RoleName.WORKFLOW_ARCHITECT,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
        assigned_by="admin",
    )
    repository.add_permission_grant(
        PermissionGrant(
            participant_id="architect",
            permission=PermissionName.PATCH_PANEL_DISCOVER,
            scope=Scope.development_global(),
        )
    )
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
    metadata = PatchPanelRegistryMetadata(
        name="Candidate",
        tags=["candidate"],
        input_types=["brief"],
        output_types=["artifact"],
        status=PatchPanelRegistryStatus.REVIEW,
    )

    proposal_response = client.post(
        "/registry/patchpanels/proposals",
        json={
            "proposal_type": "create",
            "proposed_by": "architect",
            "candidate_definition": patch_panel.model_dump(mode="json"),
            "registry_metadata": metadata.model_dump(mode="json"),
        },
        headers={"X-Ghostmesh-Participant": "architect"},
    )
    discover_response = client.get(
        f"/registry/patchpanels/proposals/{proposal_response.json()['id']}",
        headers={"X-Ghostmesh-Participant": "architect"},
    )
    promote_response = client.post(
        f"/registry/patchpanels/proposals/{proposal_response.json()['id']}/approve",
        json={"reason": "self promote"},
        headers={"X-Ghostmesh-Participant": "architect"},
    )

    assert proposal_response.status_code == 200, proposal_response.text
    assert discover_response.status_code == 200, discover_response.text
    assert promote_response.status_code == 403
    assert promote_response.json() == {"detail": "no matching permission grant"}


def test_shadow_participant_cannot_execute_production_sink() -> None:
    runtime = InMemoryCardRuntime()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    card = runtime.create_card(patch_panel_id="hello_world", payload={"title": "sink blocked"})
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="shadow-worker", type=ParticipantType.AGENT)]
    )
    assign_role_to_participant(
        repository,
        participant_id="shadow-worker",
        role_name=RoleName.SHADOW_PARTICIPANT,
        scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
    )
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            authorization_service=AuthorizationService(repository),
        )
    )

    response = client.post(
        "/nodes/sink/execute",
        json={
            "patch_panel_id": "hello_world",
            "card_id": str(card.id),
            "sink_id": "archive_sink",
        },
        headers={"X-Ghostmesh-Participant": "shadow-worker"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "no matching permission grant"}


def test_genesis_audit_payloads_store_references_not_raw_intent_goal() -> None:
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
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            registry=InMemoryPatchPanelRegistry(),
            proposal_store=InMemoryPatchPanelProposalStore(),
            authorization_service=AuthorizationService(repository),
        )
    )

    response = client.post(
        "/genesis/intents",
        json={
            "requested_by": "intent-operator",
            "deduplication_key": "sensitive-intent",
            "goal": "sensitive customer-specific launch plan",
            "input_type": "campaign_brief",
            "desired_outputs": ["artifact"],
            "tags": ["campaign"],
        },
        headers={"X-Ghostmesh-Participant": "intent-operator"},
    )

    assert response.status_code == 200, response.text
    genesis_events = [
        event
        for event in repository.audit_events
        if event.action == AuditAction.GENESIS_DESIGN_REQUIRED
    ]
    assert genesis_events
    assert "goal" not in genesis_events[0].metadata
    assert genesis_events[0].target_ref == response.json()["id"]


def test_phase10_docs_are_linked_from_readme() -> None:
    root = EXAMPLES.parents[1]
    readme = (root / "README.md").read_text()

    assert "Do not orchestrate agents. Choreograph work." in readme
    assert "`Participant` records" in readme
    assert "Routing Validators (Junctions)" in readme
    assert "docs/participant_authority_architecture.md" in readme
    assert "docs/patch_panel_registry_architecture.md" in readme
    assert "docs/intent_driven_genesis_architecture.md" in readme
