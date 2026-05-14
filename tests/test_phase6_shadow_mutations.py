from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.domain import MutationStatus
from ghostmesh.nodes import NodeExecutor
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime, ShadowPolicy, ShadowService
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_shadow_cards_are_linked_and_cannot_execute_production_sink() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(patch_panel)
    production = runtime.create_card(patch_panel_id="hello_world", payload={"title": "prod"})
    shadow_service = ShadowService(runtime)

    run = shadow_service.create_shadow_card(
        production_card=production,
        candidate_id="candidate-worker",
    )
    link_id = UUID(run.shadow_metadata["shadow_link_id"])
    completed = shadow_service.complete_shadow(
        link_id=link_id,
        metrics={"latency_ms": 12, "accepted": True},
    )

    assert run.shadow_card.metadata["shadow"] is True
    assert run.shadow_card.metadata["production_card_id"] == str(production.id)
    assert completed.status == "completed"
    assert completed.metrics["latency_ms"] == 12
    assert "shadow_created" in [event.event_type for event in runtime.card_history(production.id)]
    assert link_id

    executor = NodeExecutor(patch_panel=patch_panel, runtime=runtime)
    with pytest.raises(InvalidOperationError, match="shadow cards cannot execute"):
        executor.execute_sink(card_id=run.shadow_card.id, sink_id="archive_sink")


def test_shadow_sampling_and_parallel_limits_are_enforced() -> None:
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))
    production = runtime.create_card(patch_panel_id="hello_world", payload={"title": "prod"})
    shadow_service = ShadowService(runtime)

    with pytest.raises(InvalidOperationError, match="sampling skipped"):
        shadow_service.create_shadow_card(
            production_card=production,
            candidate_id="skipped",
            policy=ShadowPolicy(sample_rate=0, max_parallel=1),
        )

    shadow_service.create_shadow_card(
        production_card=production,
        candidate_id="first",
        policy=ShadowPolicy(sample_rate=1, max_parallel=1),
    )
    with pytest.raises(ConflictError, match="maximum parallel"):
        shadow_service.create_shadow_card(
            production_card=production,
            candidate_id="second",
            policy=ShadowPolicy(sample_rate=1, max_parallel=1),
        )


def test_mutations_must_be_validated_before_promotion() -> None:
    runtime = InMemoryCardRuntime()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    shadow_service = ShadowService(runtime)
    mutation = shadow_service.propose_mutation(
        mutation_type="route",
        proposed_by="learning_node",
        payload={"change": "prefer cheaper worker"},
    )

    with pytest.raises(ConflictError, match="validated"):
        shadow_service.promote_mutation(mutation_id=mutation.id, patch_panel=patch_panel)

    validated = shadow_service.validate_mutation(
        mutation_id=mutation.id,
        accepted=True,
        validator_id="mutation_validator",
        reason="Shadow metrics improved",
    )
    promoted = shadow_service.promote_mutation(mutation_id=mutation.id, patch_panel=patch_panel)

    assert validated.status == MutationStatus.VALIDATED
    assert promoted.status == MutationStatus.PROMOTED
    assert promoted.promoted_at is not None


def test_shadow_and_mutation_api_surface() -> None:
    runtime = InMemoryCardRuntime()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    production = runtime.create_card(patch_panel_id="hello_world", payload={"title": "api"})
    client = TestClient(create_app(runtime=runtime))

    shadow_response = client.post(
        "/shadows",
        json={
            "production_card_id": str(production.id),
            "candidate_id": "api-shadow",
            "sample_rate": 1,
            "max_parallel": 1,
        },
    )
    assert shadow_response.status_code == 200, shadow_response.text
    link_id = shadow_response.json()["shadow_metadata"]["shadow_link_id"]

    complete_response = client.post(
        f"/shadows/{link_id}/complete",
        json={"metrics": {"accepted": True, "cost": 0.1}},
    )
    assert complete_response.status_code == 200, complete_response.text
    assert complete_response.json()["metrics"]["accepted"] is True

    mutation_response = client.post(
        "/mutations",
        json={
            "mutation_type": "prompt",
            "proposed_by": "learning_node",
            "payload": {"prompt": "v2"},
        },
    )
    mutation_id = mutation_response.json()["id"]
    validate_response = client.post(
        f"/mutations/{mutation_id}/validate",
        json={"accepted": True, "validator_id": "mutation_validator"},
    )
    promote_response = client.post(
        f"/mutations/{mutation_id}/promote",
        json={"patch_panel": patch_panel.model_dump(mode="json", by_alias=True)},
    )

    assert mutation_response.status_code == 200, mutation_response.text
    assert validate_response.status_code == 200, validate_response.text
    assert promote_response.status_code == 200, promote_response.text
    assert promote_response.json()["status"] == "promoted"
