from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine, inspect, select

from ghostmesh.auth import AuthorizationService, PostgresAuthorizationRepository
from ghostmesh.domain import PermissionName, Scope, ScopeType
from ghostmesh.persistence.tables import (
    authorization_audit_events,
    card_events,
    cards,
    leases,
    metadata,
    participant_roles,
    participants,
    patch_panel_registry_entries,
    permission_grants,
    roles,
    validation_results,
)
from tests.helpers import seed_authority_fixture


def test_authority_tables_can_be_seeded_in_postgres_style_schema() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)

    with engine.begin() as connection:
        participant, role = seed_authority_fixture(connection)
        connection.execute(
            patch_panel_registry_entries.insert().values(
                id=uuid4(),
                patch_panel_id="hello_world",
                version="1.0.0",
                name="Hello World",
                description="Fixture registry row",
                tags=["example"],
                input_types=["text"],
                output_types=["reviewed_text"],
                required_tools=["artifact_store"],
                required_permissions=["card:create", "card:claim"],
                risk_level="low",
                estimated_cost="low",
                estimated_latency="minutes",
                owner_participant_id=participant.id,
                status="published",
                supersedes_entry_id=None,
                registry_metadata={"fixture": True},
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                archived_at=None,
            )
        )

        participant_row = connection.execute(
            select(participants.c.type, participants.c.status).where(
                participants.c.id == participant.id
            )
        ).one()
        role_row = connection.execute(select(roles.c.name).where(roles.c.id == role.id)).one()
        assignment_row = connection.execute(
            select(participant_roles.c.scope_type, participant_roles.c.scope_id)
        ).one()
        grant_row = connection.execute(select(permission_grants.c.permission)).one()
        audit_row = connection.execute(
            select(authorization_audit_events.c.action, authorization_audit_events.c.allowed)
        ).one()
        registry_row = connection.execute(
            select(
                patch_panel_registry_entries.c.status,
                patch_panel_registry_entries.c.owner_participant_id,
            )
        ).one()

    assert participant_row == ("script", "active")
    assert role_row.name == "worker"
    assert assignment_row == ("workflow", "fixture-workflow")
    assert grant_row.permission == "card:claim"
    assert audit_row == ("authorization:allowed", True)
    assert registry_row == ("published", participant.id)


def test_runtime_identity_bridge_columns_are_nullable_and_non_breaking() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)

    card_id = uuid4()
    lease_id = uuid4()
    validation_id = uuid4()
    event_id = uuid4()

    with engine.begin() as connection:
        connection.execute(
            cards.insert().values(
                id=card_id,
                workflow_version="hello_world:1.0.0",
                current_bucket="worker_inbox",
                payload={"title": "legacy compatible"},
                card_metadata={},
                created_at=datetime.now(UTC),
            )
        )
        connection.execute(
            leases.insert().values(
                id=lease_id,
                card_id=card_id,
                node_id="worker",
                worker_id="legacy-worker",
                participant_id=None,
                input_pipe="worker_input",
                claimed_at=datetime.now(UTC),
                expires_at=datetime.now(UTC),
                released_at=None,
            )
        )
        connection.execute(
            validation_results.insert().values(
                id=validation_id,
                card_id=card_id,
                validator_id="legacy-validator",
                participant_id=None,
                accepted=True,
                reason=None,
                payload={},
                created_at=datetime.now(UTC),
            )
        )
        connection.execute(
            card_events.insert().values(
                id=event_id,
                card_id=card_id,
                event_type="card_claimed",
                actor_id="legacy-worker",
                participant_id=None,
                payload={},
                occurred_at=datetime.now(UTC),
            )
        )

        lease_row = connection.execute(
            select(leases.c.worker_id, leases.c.participant_id)
        ).one()
        validation_row = connection.execute(
            select(validation_results.c.validator_id, validation_results.c.participant_id)
        ).one()
        event_row = connection.execute(
            select(card_events.c.actor_id, card_events.c.participant_id)
        ).one()

    assert lease_row == ("legacy-worker", None)
    assert validation_row == ("legacy-validator", None)
    assert event_row == ("legacy-worker", None)


def test_authority_metadata_matches_expected_table_names() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    table_names = set(inspect(engine).get_table_names())

    assert {
        "participants",
        "roles",
        "participant_roles",
        "permission_grants",
        "authorization_audit_events",
        "patch_panel_registry_entries",
    }.issubset(table_names)


def test_postgres_authorization_repository_reads_seeded_grants() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as connection:
        participant, _role = seed_authority_fixture(connection)

    service = AuthorizationService(PostgresAuthorizationRepository(engine))
    decision = service.authorize(
        participant_id=participant.id,
        permission=PermissionName.CARD_CLAIM,
        scope=Scope(type=ScopeType.BUCKET, id="fixture-bucket"),
        context={"workflow_id": "fixture-workflow"},
    )

    with engine.connect() as connection:
        audit_rows = connection.execute(select(authorization_audit_events.c.allowed)).all()

    assert decision.allowed is True
    assert audit_rows[-1].allowed is True
