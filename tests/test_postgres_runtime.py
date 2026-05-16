from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, select

from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.persistence.tables import (
    artifacts,
    card_events,
    card_locations,
    metadata,
    validation_results,
)
from ghostmesh.runtime import PostgresCardRuntime
from tests.helpers import artifact_ref

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_postgres_runtime_persists_card_location_and_evidence() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    runtime = PostgresCardRuntime(engine)
    runtime.register_patch_panel(load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml"))

    card = runtime.create_card(
        patch_panel_id="hello_world",
        payload={"title": "durable card"},
        metadata={"priority": "normal"},
        idempotency_key="create-durable-1",
    )
    same_card = runtime.create_card(
        patch_panel_id="hello_world",
        payload={"title": "ignored"},
        idempotency_key="create-durable-1",
    )
    lease = runtime.claim_card(
        input_pipe="worker_input",
        worker_id="postgres-worker",
        idempotency_key="claim-durable-1",
    )
    same_lease = runtime.claim_card(
        input_pipe="worker_input",
        worker_id="postgres-worker",
        idempotency_key="claim-durable-1",
    )
    artifact_refs = runtime.submit_artifact(
        lease_id=lease.id,
        output_pipe="worker_output",
        artifact_refs=[artifact_ref(card.id)],
        idempotency_key="submit-durable-1",
    )
    validation_event = runtime.validate_card(
        card_id=card.id,
        validator_id="human_validator",
        accepted=True,
        output_pipe="publish",
        idempotency_key="validate-durable-1",
    )
    history = runtime.card_history(card.id)

    with engine.connect() as connection:
        event_count = connection.execute(select(card_events.c.id)).all()
        locations = connection.execute(
            select(card_locations.c.bucket, card_locations.c.status).where(
                card_locations.c.card_id == card.id
            )
        ).all()
        artifact_rows = connection.execute(select(artifacts)).all()
        validation_rows = connection.execute(select(validation_results)).all()

    assert same_card.id == card.id
    assert same_lease.id == lease.id
    assert artifact_refs[0].card_id == card.id
    assert artifact_refs[0].content_hash.startswith("sha256:")
    assert validation_event.payload["output_pipe"] == "publish"
    assert artifact_rows[0]._mapping["storage_ref"].startswith("git:working-tree:")
    assert validation_rows[0]._mapping["output_pipe"] == "publish"
    assert "payload" not in artifacts.c
    assert [event.event_type for event in history] == [
        "card_created",
        "card_claimed",
        "artifact_submitted",
        "card_moved",
        "card_validated",
    ]
    assert len(event_count) == 5
    assert ("worker_inbox", "exited") in locations
    assert ("validation_inbox", "exited") in locations
    assert ("done", "active") in locations
