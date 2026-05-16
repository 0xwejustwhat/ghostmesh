from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.nodes import HumanValidationInput, NodeExecutor, WorkerExecutionInput
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime
from tests.helpers import artifact_ref

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_node_executor_runs_canonical_workflow_to_sink() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(patch_panel)
    executor = NodeExecutor(patch_panel=patch_panel, runtime=runtime)

    card = executor.execute_source(
        source_id="intake_source",
        payload={"title": "Node execution"},
    )
    artifact_refs = executor.execute_worker(
        WorkerExecutionInput(
            input_pipe="worker_input",
            output_pipe="worker_output",
            worker_id="worker-1",
            artifact_refs=[artifact_ref(card.id)],
        )
    )
    validation = executor.execute_human_validator(
        HumanValidationInput(
            card_id=card.id,
            validator_id="human_validator",
            accepted=True,
            score=9,
            reason="Looks good",
        )
    )
    decision = executor.execute_junction(card_id=card.id, junction_id="routing_junction")
    sink = executor.execute_sink(
        card_id=card.id,
        sink_id="archive_sink",
        external_reference="archive://card",
    )

    assert artifact_refs[0].card_id == card.id
    assert validation.payload["accepted"] is True
    assert decision.selected_bucket == "done"
    assert sink.external_reference == "archive://card"
    assert [event.event_type for event in runtime.card_history(card.id)] == [
        "card_created",
        "source_executed",
        "card_claimed",
        "artifact_submitted",
        "card_validated",
        "card_moved",
        "junction_routed",
        "sink_executed",
    ]


def test_junction_routes_rejected_cards_to_rejected_bucket() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(patch_panel)
    executor = NodeExecutor(patch_panel=patch_panel, runtime=runtime)
    card = executor.execute_source(source_id="intake_source", payload={"title": "Reject"})

    executor.execute_human_validator(
        HumanValidationInput(
            card_id=card.id,
            validator_id="human_validator",
            accepted=False,
            score=3,
            reason="Not ready",
        )
    )
    decision = executor.execute_junction(card_id=card.id, junction_id="routing_junction")

    assert decision.selected_pipe == "junction_reject"
    assert decision.selected_bucket == "rejected"
    assert decision.card.current_bucket == "rejected"


def test_node_execution_api_runs_source_worker_validator_junction_sink() -> None:
    runtime = InMemoryCardRuntime()
    client = TestClient(create_app(runtime=runtime))
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    register_response = client.post("/patchpanels", json=patch_panel.model_dump(mode="json"))
    assert register_response.status_code == 200, register_response.text

    source_response = client.post(
        "/nodes/source/execute",
        json={
            "patch_panel_id": "hello_world",
            "source_id": "intake_source",
            "payload": {"title": "API workflow"},
        },
    )
    assert source_response.status_code == 200, source_response.text
    card_id = source_response.json()["id"]

    worker_response = client.post(
        "/nodes/worker/execute",
        json={
            "patch_panel_id": "hello_world",
            "input_pipe": "worker_input",
            "output_pipe": "worker_output",
            "worker_id": "api-worker",
            "artifact_refs": [artifact_ref(card_id=card_id).model_dump(mode="json")],
        },
    )
    validator_response = client.post(
        "/nodes/validator/human/execute",
        json={
            "patch_panel_id": "hello_world",
            "card_id": card_id,
            "validator_id": "human_validator",
            "accepted": True,
            "score": 8,
            "reason": "accepted",
        },
    )
    junction_response = client.post(
        "/nodes/junction/execute",
        json={
            "patch_panel_id": "hello_world",
            "card_id": card_id,
            "junction_id": "routing_junction",
        },
    )
    sink_response = client.post(
        "/nodes/sink/execute",
        json={
            "patch_panel_id": "hello_world",
            "card_id": card_id,
            "sink_id": "archive_sink",
            "external_reference": "archive://api-card",
        },
    )

    assert worker_response.status_code == 200, worker_response.text
    assert validator_response.status_code == 200, validator_response.text
    assert junction_response.status_code == 200, junction_response.text
    assert sink_response.status_code == 200, sink_response.text
    assert junction_response.json()["selected_bucket"] == "done"
    assert sink_response.json()["external_reference"] == "archive://api-card"
