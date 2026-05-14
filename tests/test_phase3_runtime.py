from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from ghostmesh.api.main import create_app
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.persistence.tables import metadata
from ghostmesh.runtime import InMemoryCardRuntime, PostgresCardRuntime
from ghostmesh.runtime.errors import ConflictError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_postgres_runtime_renews_releases_and_recovers_expired_leases() -> None:
    runtime = _postgres_runtime()
    card = runtime.create_card(patch_panel_id="hello_world", payload={"task": "lease lifecycle"})
    lease = runtime.claim_card(input_pipe="worker_input", worker_id="worker-a")

    renewed = runtime.renew_lease(
        lease_id=lease.id,
        lease_seconds=900,
        idempotency_key="renew-1",
    )
    same_renewal = runtime.renew_lease(
        lease_id=lease.id,
        lease_seconds=120,
        idempotency_key="renew-1",
    )
    released = runtime.release_lease(lease_id=lease.id, actor_id="worker-a")
    replacement = runtime.claim_card(input_pipe="worker_input", worker_id="worker-b")

    assert renewed.id == lease.id
    assert same_renewal.expires_at.replace(tzinfo=None) == renewed.expires_at.replace(tzinfo=None)
    assert released.released_at is not None
    assert replacement.card_id == card.id
    assert [event.event_type for event in runtime.card_history(card.id)] == [
        "card_created",
        "card_claimed",
        "lease_renewed",
        "lease_released",
        "card_claimed",
    ]


def test_postgres_runtime_expired_lease_blocks_submit_and_can_be_reclaimed() -> None:
    runtime = _postgres_runtime()
    card = runtime.create_card(patch_panel_id="hello_world", payload={"task": "expiry"})
    expired_lease = runtime.claim_card(
        input_pipe="worker_input",
        worker_id="slow-worker",
        lease_seconds=-1,
    )

    with pytest.raises(ConflictError, match="expired"):
        runtime.submit_artifact(
            lease_id=expired_lease.id,
            output_pipe="worker_output",
            payload={"draft": "too late"},
        )

    expired = runtime.expire_leases()
    replacement = runtime.claim_card(input_pipe="worker_input", worker_id="fresh-worker")

    assert [lease.id for lease in expired] == [expired_lease.id]
    assert replacement.card_id == card.id
    assert "lease_expired" in [event.event_type for event in runtime.card_history(card.id)]


def test_postgres_runtime_submit_is_idempotent_and_releases_lease() -> None:
    runtime = _postgres_runtime()
    card = runtime.create_card(patch_panel_id="hello_world", payload={"task": "submit"})
    lease = runtime.claim_card(input_pipe="worker_input", worker_id="worker-a")

    artifact = runtime.submit_artifact(
        lease_id=lease.id,
        output_pipe="worker_output",
        payload={"draft": "first"},
        idempotency_key="submit-1",
    )
    same_artifact = runtime.submit_artifact(
        lease_id=lease.id,
        output_pipe="worker_output",
        payload={"draft": "second"},
        idempotency_key="submit-1",
    )

    assert same_artifact.id == artifact.id
    assert runtime.list_cards()[0].current_bucket == "validation_inbox"
    assert [event.event_type for event in runtime.card_history(card.id)] == [
        "card_created",
        "card_claimed",
        "artifact_submitted",
    ]


def test_api_exposes_lease_renew_release_and_expire() -> None:
    runtime = InMemoryCardRuntime()
    client = TestClient(create_app(runtime=runtime))
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))
    runtime.create_card(patch_panel_id="hello_world", payload={"task": "api leases"})
    lease = runtime.claim_card(input_pipe="worker_input", worker_id="api-worker")

    renew_response = client.post(
        f"/leases/{lease.id}/renew",
        json={"lease_seconds": 600},
        headers={"Idempotency-Key": "api-renew-1"},
    )
    release_response = client.post(
        f"/leases/{lease.id}/release",
        json={"actor_id": "api-worker"},
        headers={"Idempotency-Key": "api-release-1"},
    )
    expire_response = client.post("/leases/expire")

    assert renew_response.status_code == 200, renew_response.text
    assert release_response.status_code == 200, release_response.text
    assert expire_response.status_code == 200, expire_response.text
    assert release_response.json()["released_at"] is not None


def _postgres_runtime() -> PostgresCardRuntime:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    runtime = PostgresCardRuntime(engine)
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))
    return runtime
