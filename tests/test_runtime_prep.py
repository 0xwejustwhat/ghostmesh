from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime, ShadowHarness
from tests.helpers import artifact_ref

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_runtime_claim_submit_validate_move_flow() -> None:
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))

    card = runtime.create_card(
        patch_panel_id="hello_world",
        payload={"title": "Phase 2 prep"},
        idempotency_key="create-1",
    )
    same_card = runtime.create_card(
        patch_panel_id="hello_world",
        payload={"title": "ignored by idempotency"},
        idempotency_key="create-1",
    )
    lease = runtime.claim_card(
        input_pipe="worker_input",
        worker_id="worker-a",
        idempotency_key="claim-1",
    )
    artifact_refs = runtime.submit_artifact(
        lease_id=lease.id,
        output_pipe="worker_output",
        artifact_refs=[artifact_ref(card.id)],
        idempotency_key="submit-1",
    )
    event = runtime.validate_card(
        card_id=card.id,
        validator_id="human_validator",
        accepted=True,
        output_pipe="validator_reviewed",
        idempotency_key="validate-1",
    )

    assert same_card.id == card.id
    assert artifact_refs[0].card_id == card.id
    assert artifact_refs[0].storage_ref.startswith("git:working-tree:")
    assert event.payload["accepted"] is True
    assert runtime.list_cards()[0].current_bucket == "junction_inbox"
    assert [entry.event_type for entry in runtime.card_history(card.id)] == [
        "card_created",
        "card_claimed",
        "artifact_submitted",
        "card_validated",
    ]


def test_api_exposes_patchpanel_card_claim_and_submit() -> None:
    runtime = InMemoryCardRuntime()
    client = TestClient(create_app(runtime=runtime))
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    register_response = client.post("/patchpanels", json=patch_panel.model_dump(mode="json"))
    assert register_response.status_code == 200, register_response.text

    create_response = client.post(
        "/cards",
        json={"patch_panel_id": "hello_world", "payload": {"title": "API card"}},
        headers={"Idempotency-Key": "api-create-1"},
    )
    assert create_response.status_code == 200, create_response.text

    claim_response = client.post(
        "/cards/claim",
        json={"input_pipe": "worker_input", "worker_id": "worker-api"},
        headers={"Idempotency-Key": "api-claim-1"},
    )
    assert claim_response.status_code == 200, claim_response.text

    submit_response = client.post(
        "/cards/submit",
        json={
            "lease_id": claim_response.json()["id"],
            "output_pipe": "worker_output",
            "artifact_refs": [
                artifact_ref(card_id=create_response.json()["id"]).model_dump(mode="json")
            ],
        },
        headers={"Idempotency-Key": "api-submit-1"},
    )

    assert submit_response.status_code == 200, submit_response.text
    assert submit_response.json()[0]["metadata"]["role"] == "draft"


def test_shadow_harness_creates_linked_isolated_shadow_card() -> None:
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))
    production_card = runtime.create_card(
        patch_panel_id="hello_world",
        payload={"title": "Production"},
    )

    shadow_run = ShadowHarness(runtime).create_shadow_card(
        production_card=production_card,
        candidate_id="candidate-worker-v2",
    )

    assert shadow_run.shadow_card.id != production_card.id
    assert shadow_run.shadow_card.payload == production_card.payload
    assert shadow_run.shadow_card.metadata["shadow"] is True
    assert shadow_run.shadow_card.metadata["production_card_id"] == str(production_card.id)
    assert production_card.metadata == {}
