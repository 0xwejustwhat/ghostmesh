from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime
from tests.helpers import artifact_ref

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_worker_context_endpoint_returns_claimed_card_and_history() -> None:
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))
    card = runtime.create_card(patch_panel_id="hello_world", payload={"title": "context"})
    lease = runtime.claim_card(input_pipe="worker_input", worker_id="worker-1")
    client = TestClient(create_app(runtime=runtime))

    response = client.get(f"/workers/leases/{lease.id}/context")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["lease"]["id"] == str(lease.id)
    assert payload["card"]["id"] == str(card.id)
    assert [event["event_type"] for event in payload["history"]] == [
        "card_created",
        "card_claimed",
    ]


def test_human_validator_can_list_inspect_and_decide_reviewable_cards() -> None:
    runtime = InMemoryCardRuntime()
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    card = runtime.create_card(patch_panel_id="hello_world", payload={"title": "review"})
    lease = runtime.claim_card(input_pipe="worker_input", worker_id="worker-1")
    runtime.submit_artifact(
        lease_id=lease.id,
        output_pipe="worker_output",
        artifact_refs=[artifact_ref(card.id)],
    )
    client = TestClient(create_app(runtime=runtime))

    list_response = client.get(
        "/validators/human_validator/cards",
        params={"patch_panel_id": "hello_world"},
    )
    inspect_response = client.get(f"/validators/cards/{card.id}")
    decision_response = client.post(
        f"/validators/human_validator/cards/{card.id}/decision",
        json={
            "patch_panel_id": "hello_world",
            "accepted": True,
            "score": 9,
            "reason": "Approved",
        },
        headers={"Idempotency-Key": "validator-decision-1"},
    )

    assert list_response.status_code == 200, list_response.text
    assert [item["id"] for item in list_response.json()] == [str(card.id)]
    assert inspect_response.status_code == 200, inspect_response.text
    assert inspect_response.json()["card"]["payload"] == {"title": "review"}
    assert decision_response.status_code == 200, decision_response.text
    assert decision_response.json()["payload"]["accepted"] is True
    assert "card_validated" in [event.event_type for event in runtime.card_history(card.id)]
