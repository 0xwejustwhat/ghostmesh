from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from ghostmesh.api.main import create_app
from ghostmesh.boundaries import BoundaryAdapterService, BoundarySinkRequest, BoundarySourceRequest
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_webhook_source_maps_payload_and_deduplicates_external_events() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "webhook-boundary-patchpanel.yaml")
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(patch_panel)
    service = BoundaryAdapterService(runtime=runtime)

    request = BoundarySourceRequest(
        patch_panel_id="webhook_boundary",
        source_id="github_issue_source",
        actor_token="dev-webhook-token",
        headers={"X-GitHub-Delivery": "delivery-1"},
        external_payload=_github_issue_payload(),
    )

    first = service.execute_source(request)
    duplicate = service.execute_source(request)

    assert duplicate.card.id == first.card.id
    assert first.deduplication_key == "delivery-1"
    assert first.card.payload == {
        "title": "Boundary adapters",
        "body": "Wire Source and Sink edges.",
        "external_url": "https://github.com/acme/ghostmesh/issues/7",
    }
    assert first.card.metadata["repository"] == "acme/ghostmesh"
    assert [event.event_type for event in runtime.card_history(first.card.id)] == [
        "card_created",
        "source_executed",
        "boundary_source_received",
    ]


def test_sink_boundary_records_external_reference_and_prevents_duplicate_egress() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "webhook-boundary-patchpanel.yaml")
    runtime = InMemoryCardRuntime()
    runtime.register_patch_panel(patch_panel)
    service = BoundaryAdapterService(runtime=runtime)
    card = service.execute_source(
        BoundarySourceRequest(
            patch_panel_id="webhook_boundary",
            source_id="github_issue_source",
            actor_token="dev-webhook-token",
            headers={"X-GitHub-Delivery": "delivery-2"},
            external_payload=_github_issue_payload(),
        )
    ).card

    request = BoundarySinkRequest(
        patch_panel_id="webhook_boundary",
        sink_id="notification_sink",
        card_id=card.id,
        actor_token="dev-egress-token",
        external_response={"message_ts": "slack://C123/1710000000.000001"},
    )
    first = service.execute_sink(request)
    duplicate = service.execute_sink(request)

    assert duplicate.event.id == first.event.id
    assert first.external_reference == "slack://C123/1710000000.000001"
    assert first.egress_idempotency_key == f"{card.id}:notification_sink"
    assert [event.event_type for event in runtime.card_history(card.id)] == [
        "card_created",
        "source_executed",
        "boundary_source_received",
        "sink_executed",
        "boundary_sink_egressed",
    ]


def test_boundary_api_surface_and_authorization() -> None:
    runtime = InMemoryCardRuntime()
    patch_panel = load_patch_panel(EXAMPLES / "webhook-boundary-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    client = TestClient(create_app(runtime=runtime))

    denied = client.post(
        "/boundaries/source",
        json={
            "patch_panel_id": "webhook_boundary",
            "source_id": "github_issue_source",
            "actor_token": "wrong",
            "headers": {"X-GitHub-Delivery": "api-delivery-denied"},
            "external_payload": _github_issue_payload(),
        },
    )
    accepted = client.post(
        "/boundaries/source",
        json={
            "patch_panel_id": "webhook_boundary",
            "source_id": "github_issue_source",
            "actor_token": "dev-webhook-token",
            "headers": {"X-GitHub-Delivery": "api-delivery-1"},
            "external_payload": _github_issue_payload(),
        },
    )
    card_id = accepted.json()["card"]["id"]
    egress = client.post(
        "/boundaries/sink",
        json={
            "patch_panel_id": "webhook_boundary",
            "sink_id": "notification_sink",
            "card_id": card_id,
            "actor_token": "dev-egress-token",
            "external_response": {"message_ts": "slack://api/message"},
        },
    )

    assert denied.status_code == 422, denied.text
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["deduplication_key"] == "api-delivery-1"
    assert egress.status_code == 200, egress.text
    assert egress.json()["external_reference"] == "slack://api/message"


def _github_issue_payload() -> dict[str, object]:
    return {
        "issue": {
            "title": "Boundary adapters",
            "body": "Wire Source and Sink edges.",
            "html_url": "https://github.com/acme/ghostmesh/issues/7",
        },
        "repository": {"full_name": "acme/ghostmesh"},
        "sender": {"login": "octocat"},
    }
