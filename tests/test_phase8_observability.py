from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.nodes import HumanValidationInput, NodeExecutor, WorkerExecutionInput
from ghostmesh.observability import ObservabilityService
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime
from tests.helpers import artifact_ref

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_observability_service_reports_topology_load_leases_and_metrics() -> None:
    runtime, card = _runtime_with_workflow()
    service = ObservabilityService(runtime=runtime)

    topology = service.topology("hello_world")
    load = service.bucket_load()
    activity = service.worker_activity()
    decisions = service.validator_decisions()
    metrics = service.metrics()

    assert "flowchart LR" in topology["mermaid"]
    assert any(node["id"] == "archive_sink" for node in topology["nodes"])
    assert load == {"done": 1}
    assert service.active_leases() == []
    assert activity["worker-1"]["card_claimed"] == 1
    assert activity["worker-1"]["artifact_submitted"] == 1
    assert decisions[0]["card_id"] == card.id
    assert decisions[0]["accepted"] is True
    assert metrics["card_count"] == 1
    assert metrics["acceptance_rate"] == 1
    assert metrics["event_counts"]["sink_executed"] == 1


def test_observability_api_exposes_read_only_operator_views() -> None:
    runtime, _card = _runtime_with_workflow()
    client = TestClient(create_app(runtime=runtime))

    topology = client.get("/ops/topology/hello_world")
    load = client.get("/ops/buckets/load")
    active_leases = client.get("/ops/leases/active")
    activity = client.get("/ops/workers/activity")
    decisions = client.get("/ops/validators/decisions")
    versions = client.get("/ops/workflow-versions")
    failed = client.get("/ops/failed-movements")
    metrics = client.get("/ops/metrics")
    dashboard = client.get("/ops/dashboard/hello_world")

    assert topology.status_code == 200, topology.text
    assert load.json() == {"done": 1}
    assert active_leases.json() == []
    assert activity.json()["worker-1"]["artifact_submitted"] == 1
    assert decisions.json()[0]["accepted"] is True
    assert versions.json()[0]["id"] == "hello_world:1.0.0"
    assert failed.json() == []
    assert metrics.json()["active_lease_count"] == 0
    assert dashboard.json()["bucket_load"] == {"done": 1}


def test_active_lease_operator_view_shows_age_and_expiry() -> None:
    runtime = InMemoryCardRuntime()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    card = runtime.create_card(patch_panel_id="hello_world", payload={"title": "Claimed"})
    lease = runtime.claim_card(input_pipe="worker_input", worker_id="worker-1")

    active = ObservabilityService(runtime=runtime).active_leases()

    assert active[0]["lease"].id == lease.id
    assert active[0]["lease"].card_id == card.id
    assert active[0]["age_seconds"] >= 0
    assert active[0]["expires_in_seconds"] > 0


def _runtime_with_workflow() -> tuple[InMemoryCardRuntime, object]:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(patch_panel)
    executor = NodeExecutor(patch_panel=patch_panel, runtime=runtime)
    card = executor.execute_source(
        source_id="intake_source",
        payload={"title": "Operator view"},
    )
    executor.execute_worker(
        WorkerExecutionInput(
            input_pipe="worker_input",
            output_pipe="worker_output",
            worker_id="worker-1",
            artifact_refs=[artifact_ref(card.id)],
        )
    )
    executor.execute_human_validator(
        HumanValidationInput(
            card_id=card.id,
            validator_id="human_validator",
            accepted=True,
            score=9,
            reason="ready",
        )
    )
    executor.execute_junction(card_id=card.id, junction_id="routing_junction")
    executor.execute_sink(
        card_id=card.id,
        sink_id="archive_sink",
        external_reference="archive://operator",
    )
    return runtime, card
