from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionGrant,
    PermissionName,
    Scope,
    ScopeType,
)
from ghostmesh.nodes import NodeExecutor, ValidatorExecutionInput
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import InMemoryPatchPanelRegistry, PatchPanelRegistrySearch
from ghostmesh.runtime import InMemoryCardRuntime

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples" / "patchpanels"
SYSTEM_PP = ROOT / "src" / "ghostmesh" / "defaults" / "patchpanels" / "system-pp-approval.yaml"


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


def auth_repository() -> InMemoryAuthorizationRepository:
    return InMemoryAuthorizationRepository(
        participants=[
            Participant(id="architect", type=ParticipantType.AGENT),
            Participant(id="reviewer", type=ParticipantType.HUMAN),
            Participant(id="system-sink", type=ParticipantType.SYSTEM_SERVICE),
        ],
        permission_grants=[
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
            PermissionGrant(
                participant_id="reviewer",
                permission=PermissionName.VALIDATION_SUBMIT,
                scope=Scope.development_global(),
            ),
            PermissionGrant(
                participant_id="system-sink",
                permission=PermissionName.SINK_EXECUTE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="system_pp_approval"),
            ),
        ],
    )


def test_genesis_proposal_creates_system_approval_card() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            authorization_service=AuthorizationService(auth_repository()),
        )
    )
    intent = client.post(
        "/genesis/intents",
        json={
            "requested_by": "architect",
            "deduplication_key": "proposal-card",
            "goal": "create a generated hello workflow",
            "input_type": "brief",
            "desired_outputs": ["approved_artifact"],
            "tags": ["generated"],
        },
        headers={"X-Ghostmesh-Participant": "architect"},
    ).json()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    response = client.post(
        f"/genesis/intents/{intent['id']}/propose",
        json={
            "proposed_by": "architect",
            "candidate_definition": patch_panel.model_dump(mode="json"),
            "registry_metadata": proposal_metadata().model_dump(mode="json"),
        },
        headers={"X-Ghostmesh-Participant": "architect"},
    )

    assert response.status_code == 200, response.text
    card = response.json()
    assert card["workflow_version"] == "system_pp_approval:1.0.0"
    assert card["current_bucket"] == "topology_proposals"
    assert card["payload"]["kind"] == "patch_panel_proposal"
    assert card["payload"]["candidate_definition"]["id"] == "hello_world"
    assert client.get(
        f"/genesis/intents/{intent['id']}",
        headers={"X-Ghostmesh-Participant": "architect"},
    ).json()["proposal_card_id"] == card["id"]


def test_system_topology_validator_routes_valid_and_invalid_candidates() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    create_app(settings=Settings(), runtime=runtime, registry=registry)
    system_patch_panel = load_patch_panel(SYSTEM_PP)
    candidate = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    executor = NodeExecutor(patch_panel=system_patch_panel, runtime=runtime, registry=registry)
    valid_card = runtime.create_card(
        patch_panel_id="system_pp_approval",
        payload={
            "candidate_definition": candidate.model_dump(mode="json"),
            "registry_metadata": proposal_metadata().model_dump(mode="json"),
        },
    )
    invalid_candidate = candidate.model_copy(
        update={
            "pipe_bindings": {
                key: value
                for key, value in candidate.pipe_bindings.items()
                if key != "worker_input"
            }
        }
    )
    invalid_card = runtime.create_card(
        patch_panel_id="system_pp_approval",
        payload={
            "candidate_definition": invalid_candidate.model_dump(mode="json"),
            "registry_metadata": proposal_metadata().model_dump(mode="json"),
        },
    )

    valid_event = executor.execute_validator(
        ValidatorExecutionInput(
            card_id=valid_card.id,
            validator_id="topological_validator",
        )
    )
    invalid_event = executor.execute_validator(
        ValidatorExecutionInput(
            card_id=invalid_card.id,
            validator_id="topological_validator",
        )
    )

    assert valid_event.payload["accepted"] is True
    assert valid_event.payload["output_pipe"] == "topology_valid"
    assert runtime.get_card(valid_card.id).current_bucket == "governance_review"
    assert invalid_event.payload["accepted"] is False
    assert invalid_event.payload["output_pipe"] == "topology_invalid"
    assert runtime.get_card(invalid_card.id).current_bucket == "rejected_proposals"


def test_governance_and_registry_publication_use_generic_node_execution() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()
    create_app(settings=Settings(), runtime=runtime, registry=registry)
    system_patch_panel = load_patch_panel(SYSTEM_PP)
    candidate = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    card = runtime.create_card(
        patch_panel_id="system_pp_approval",
        payload={
            "genesis_intent_id": "intent-1",
            "candidate_definition": candidate.model_dump(mode="json"),
            "registry_metadata": proposal_metadata().model_dump(mode="json"),
        },
    )
    executor = NodeExecutor(patch_panel=system_patch_panel, runtime=runtime, registry=registry)
    executor.execute_validator(
        ValidatorExecutionInput(card_id=card.id, validator_id="topological_validator")
    )
    governance_event = executor.execute_validator(
        ValidatorExecutionInput(
            card_id=card.id,
            validator_id="governance_reviewer",
            selected_exit="proposal_approved",
            reason="approved by role-governed reviewer",
        )
    )
    sink = executor.execute_sink(card_id=card.id, sink_id="registry_publication_sink")

    assert governance_event.payload["accepted"] is True
    assert runtime.get_card(card.id).current_bucket == "registry_publication"
    assert sink.external_reference is not None
    published = [
        entry
        for entry in registry.search(PatchPanelRegistrySearch(include_archived=True))
        if entry.patch_panel_id == "hello_world"
    ]
    assert len(published) == 1
    assert published[0].status == PatchPanelRegistryStatus.PUBLISHED
    assert runtime.get_card(card.id).current_bucket == "registry_publication"


def test_removed_proposal_routes_are_absent() -> None:
    client = TestClient(create_app(settings=Settings()))

    assert client.post("/registry/patchpanels/proposals", json={}).status_code in {404, 405}
    assert client.post(
        "/registry/patchpanels/proposals/00000000-0000-0000-0000-000000000000/approve",
        json={},
    ).status_code in {404, 405}
    assert client.post(
        "/registry/patchpanels/proposals/00000000-0000-0000-0000-000000000000/reject",
        json={},
    ).status_code in {404, 405}


def test_system_bootstrap_is_idempotent() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()

    first = create_app(settings=Settings(), runtime=runtime, registry=registry)
    second = create_app(settings=Settings(), runtime=runtime, registry=registry)

    system_panels = [
        panel for panel in runtime.list_patch_panels() if panel.id == "system_pp_approval"
    ]
    assert len(system_panels) == 1
    assert len(
        [
            entry
            for entry in registry.search(
                PatchPanelRegistrySearch(include_archived=True, include_superseded=True)
            )
            if entry.patch_panel_id == "system_pp_approval"
        ]
    ) == 1
    assert first.state.system_bootstrap_results[0].registered_registry is True
    assert second.state.system_bootstrap_results[0].registered_registry is False


def test_system_bootstrap_honors_override_paths() -> None:
    runtime = InMemoryCardRuntime()
    registry = InMemoryPatchPanelRegistry()

    create_app(
        settings=Settings(
            system_patch_panel_paths=(str(EXAMPLES / "hello-world-patchpanel.yaml"),)
        ),
        runtime=runtime,
        registry=registry,
    )

    assert [panel.id for panel in runtime.list_patch_panels()] == ["hello_world"]
    assert [
        entry.patch_panel_id
        for entry in registry.search(
            PatchPanelRegistrySearch(include_archived=True, include_superseded=True)
        )
    ] == ["hello_world"]
