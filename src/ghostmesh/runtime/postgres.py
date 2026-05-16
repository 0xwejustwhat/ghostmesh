from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ghostmesh.domain import ArtifactReference, Card, CardEvent, Lease, PatchPanel, ValidationResult
from ghostmesh.persistence.tables import (
    artifacts,
    buckets,
    card_events,
    card_locations,
    cards,
    idempotency_records,
    leases,
    patch_panels,
    validation_results,
    workflow_versions,
)
from ghostmesh.runtime.errors import ConflictError, NotFoundError
from ghostmesh.runtime.service import (
    ensure_active_lease,
    ensure_artifact_refs_belong_to_card,
    ensure_artifacts_accepted,
    ensure_bucket_exists,
    new_lease,
    resolve_initial_bucket,
    resolve_pipe_bucket,
    validate_patch_panel,
)


class PostgresCardRuntime:
    """Durable Phase 2 runtime backed by Postgres via SQLAlchemy Core."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def register_patch_panel(self, patch_panel: PatchPanel) -> PatchPanel:
        validate_patch_panel(patch_panel)
        workflow_version = _workflow_version_id(patch_panel)
        now = datetime.now(UTC)

        with Session(self.engine) as session, session.begin():
            existing = session.execute(
                select(patch_panels.c.id).where(
                    patch_panels.c.id == patch_panel.id,
                    patch_panels.c.version == patch_panel.version,
                )
            ).first()
            if existing is None:
                session.execute(
                    patch_panels.insert().values(
                        id=patch_panel.id,
                        version=patch_panel.version,
                        definition=patch_panel.model_dump(mode="json", by_alias=True),
                        created_at=now,
                    )
                )

            existing_version = session.execute(
                select(workflow_versions.c.id).where(workflow_versions.c.id == workflow_version)
            ).first()
            if existing_version is None:
                session.execute(
                    workflow_versions.insert().values(
                        id=workflow_version,
                        patch_panel_id=patch_panel.id,
                        version=patch_panel.version,
                        active=True,
                        created_at=now,
                    )
                )
                for bucket in patch_panel.buckets:
                    session.execute(
                        buckets.insert().values(
                            workflow_version=workflow_version,
                            id=bucket.id,
                            definition=bucket.model_dump(mode="json"),
                            created_at=now,
                        )
                    )

        return patch_panel

    def list_patch_panels(self) -> list[PatchPanel]:
        with Session(self.engine) as session:
            rows = session.execute(select(patch_panels.c.definition)).all()
        return [PatchPanel.model_validate(row.definition) for row in rows]

    def create_card(
        self,
        *,
        patch_panel_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Card:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_card(session, UUID(cached.removeprefix("card:")))

            patch_panel = self._get_active_patch_panel(session, patch_panel_id)
            initial_bucket = resolve_initial_bucket(patch_panel)
            card = Card(
                workflow_version=_workflow_version_id(patch_panel),
                current_bucket=initial_bucket,
                payload=payload,
                metadata=metadata or {},
            )
            session.execute(
                cards.insert().values(
                    id=card.id,
                    workflow_version=card.workflow_version,
                    current_bucket=card.current_bucket,
                    payload=card.payload,
                    card_metadata=card.metadata,
                    created_at=card.created_at,
                )
            )
            session.execute(
                card_locations.insert().values(
                    id=uuid4(),
                    card_id=card.id,
                    bucket=initial_bucket,
                    status="active",
                    entered_at=card.created_at,
                    accepted_at=card.created_at,
                    exited_at=None,
                )
            )
            event = CardEvent(
                card_id=card.id,
                event_type="card_created",
                payload={
                    "patch_panel_id": patch_panel.id,
                    "version": patch_panel.version,
                    "bucket": initial_bucket,
                },
            )
            self._insert_event(session, event)
            self._store_idempotency(session, idempotency_key, "card.create", f"card:{card.id}")
            return card

    def list_cards(self) -> list[Card]:
        with Session(self.engine) as session:
            rows = session.execute(select(cards)).all()
        return [_card_from_row(row._mapping) for row in rows]

    def get_card(self, card_id: UUID) -> Card:
        with Session(self.engine) as session:
            return self._get_card(session, card_id)

    def get_lease(self, lease_id: UUID) -> Lease:
        with Session(self.engine) as session:
            return self._get_lease(session, lease_id)

    def claim_card(
        self,
        *,
        input_pipe: str,
        worker_id: str,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> Lease:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_lease(session, UUID(cached.removeprefix("lease:")))

            patch_panel = self._single_patch_panel(session)
            bucket, node_id = resolve_pipe_bucket(patch_panel, input_pipe, "input")
            card_row = session.execute(
                select(cards)
                .where(cards.c.current_bucket == bucket)
                .where(
                    ~cards.c.id.in_(
                        select(leases.c.card_id).where(
                            leases.c.released_at.is_(None),
                            leases.c.expires_at > datetime.now(UTC),
                        )
                    )
                )
                .limit(1)
                .with_for_update()
            ).first()
            if card_row is None:
                raise NotFoundError(f"no claimable cards in bucket '{bucket}'")

            card = _card_from_row(card_row._mapping)
            lease = new_lease(
                card=card,
                node_id=node_id,
                worker_id=worker_id,
                input_pipe=input_pipe,
                seconds=lease_seconds,
            )
            session.execute(
                leases.insert().values(
                    id=lease.id,
                    card_id=lease.card_id,
                    node_id=lease.node_id,
                    worker_id=lease.worker_id,
                    input_pipe=lease.input_pipe,
                    claimed_at=lease.claimed_at,
                    expires_at=lease.expires_at,
                    released_at=lease.released_at,
                )
            )
            self._insert_event(
                session,
                CardEvent(
                    card_id=card.id,
                    event_type="card_claimed",
                    actor_id=worker_id,
                    payload={"lease_id": str(lease.id), "input_pipe": input_pipe},
                ),
            )
            self._store_idempotency(session, idempotency_key, "card.claim", f"lease:{lease.id}")
            return lease

    def submit_artifact(
        self,
        *,
        lease_id: UUID,
        output_pipe: str,
        artifact_refs: list[ArtifactReference],
        idempotency_key: str | None = None,
    ) -> list[ArtifactReference]:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                if cached.startswith("artifact:"):
                    return self._get_artifacts(session, [UUID(cached.removeprefix("artifact:"))])
                return self._get_artifacts(
                    session,
                    [
                        UUID(artifact_id)
                        for artifact_id in cached.removeprefix("artifacts:").split(",")
                        if artifact_id
                    ],
                )

            lease = self._get_lease(session, lease_id)
            ensure_active_lease(lease)
            card = self._get_card(session, lease.card_id)
            patch_panel = self._get_patch_panel_for_card(session, card)
            destination_bucket, node_id = resolve_pipe_bucket(patch_panel, output_pipe, "output")
            ensure_artifact_refs_belong_to_card(card_id=card.id, artifact_refs=artifact_refs)
            ensure_artifacts_accepted(
                patch_panel,
                destination_bucket_id=destination_bucket,
                artifact_refs=artifact_refs,
            )
            if node_id != lease.node_id:
                raise ConflictError(
                    f"lease node '{lease.node_id}' cannot submit through node '{node_id}'"
                )

            self._move_card_row(
                session,
                card=card,
                to_bucket=destination_bucket,
                actor_id=lease.worker_id,
                reason="artifact_submitted",
                emit_event=False,
            )
            session.execute(
                leases.update().where(leases.c.id == lease.id).values(released_at=datetime.now(UTC))
            )
            event = CardEvent(
                card_id=card.id,
                event_type="artifact_submitted",
                actor_id=lease.worker_id,
                payload={
                    "artifact_ids": [str(ref.id) for ref in artifact_refs],
                    "artifact_refs": [
                        {
                            "id": str(ref.id),
                            "storage_ref": ref.storage_ref,
                            "content_hash": ref.content_hash,
                            "content_type": ref.content_type,
                            "size_bytes": ref.size_bytes,
                            "metadata": ref.metadata,
                        }
                        for ref in artifact_refs
                    ],
                    "lease_id": str(lease.id),
                    "output_pipe": output_pipe,
                    "destination_bucket": destination_bucket,
                },
            )
            self._insert_event(session, event)
            stored_refs = [
                ref.model_copy(update={"card_id": card.id, "event_id": event.id})
                for ref in artifact_refs
            ]
            for artifact_ref in stored_refs:
                session.execute(
                    artifacts.insert().values(
                        id=artifact_ref.id,
                        card_id=artifact_ref.card_id,
                        event_id=artifact_ref.event_id,
                        storage_ref=artifact_ref.storage_ref,
                        content_hash=artifact_ref.content_hash,
                        content_type=artifact_ref.content_type,
                        size_bytes=artifact_ref.size_bytes,
                        artifact_metadata=artifact_ref.metadata,
                        created_at=artifact_ref.created_at,
                    )
                )
            self._store_idempotency(
                session,
                idempotency_key,
                "artifact.submit",
                "artifacts:" + ",".join(str(ref.id) for ref in stored_refs),
            )
            return stored_refs

    def renew_lease(
        self,
        *,
        lease_id: UUID,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> Lease:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_lease(session, UUID(cached.removeprefix("lease:")))

            lease = self._get_lease(session, lease_id)
            ensure_active_lease(lease)
            expires_at = datetime.now(UTC) + timedelta(seconds=lease_seconds)
            session.execute(
                leases.update().where(leases.c.id == lease.id).values(expires_at=expires_at)
            )
            renewed = lease.model_copy(update={"expires_at": expires_at})
            self._insert_event(
                session,
                CardEvent(
                    card_id=lease.card_id,
                    event_type="lease_renewed",
                    actor_id=lease.worker_id,
                    payload={"lease_id": str(lease.id), "expires_at": expires_at.isoformat()},
                ),
            )
            self._store_idempotency(session, idempotency_key, "lease.renew", f"lease:{lease.id}")
            return renewed

    def release_lease(
        self,
        *,
        lease_id: UUID,
        actor_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Lease:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_lease(session, UUID(cached.removeprefix("lease:")))

            lease = self._get_lease(session, lease_id)
            if lease.released_at is not None:
                return lease
            released_at = datetime.now(UTC)
            session.execute(
                leases.update().where(leases.c.id == lease.id).values(released_at=released_at)
            )
            released = lease.model_copy(update={"released_at": released_at})
            self._insert_event(
                session,
                CardEvent(
                    card_id=lease.card_id,
                    event_type="lease_released",
                    actor_id=actor_id or lease.worker_id,
                    payload={"lease_id": str(lease.id)},
                ),
            )
            self._store_idempotency(session, idempotency_key, "lease.release", f"lease:{lease.id}")
            return released

    def expire_leases(self) -> list[Lease]:
        now = datetime.now(UTC)
        expired: list[Lease] = []
        with Session(self.engine) as session, session.begin():
            rows = session.execute(
                select(leases).where(
                    leases.c.released_at.is_(None),
                    leases.c.expires_at <= now,
                )
            ).all()
            for row in rows:
                lease = self._lease_from_row(row._mapping)
                session.execute(
                    leases.update().where(leases.c.id == lease.id).values(released_at=now)
                )
                released = lease.model_copy(update={"released_at": now})
                expired.append(released)
                self._insert_event(
                    session,
                    CardEvent(
                        card_id=lease.card_id,
                        event_type="lease_expired",
                        actor_id=lease.worker_id,
                        payload={"lease_id": str(lease.id)},
                    ),
                )
        return expired

    def validate_card(
        self,
        *,
        card_id: UUID,
        validator_id: str,
        accepted: bool,
        reason: str | None = None,
        output_pipe: str | None = None,
        idempotency_key: str | None = None,
    ) -> CardEvent:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_event(session, UUID(cached.removeprefix("event:")))

            card = self._get_card(session, card_id)
            result = ValidationResult(
                card_id=card.id,
                validator_id=validator_id,
                accepted=accepted,
                reason=reason,
                payload={"output_pipe": output_pipe} if output_pipe else {},
            )
            session.execute(
                validation_results.insert().values(
                    id=result.id,
                    card_id=result.card_id,
                    validator_id=result.validator_id,
                    accepted=result.accepted,
                    reason=result.reason,
                    payload=result.payload,
                    created_at=result.created_at,
                )
            )

            event_payload: dict[str, Any] = {
                "accepted": accepted,
                "reason": reason,
                "validation_result_id": str(result.id),
            }
            if output_pipe:
                patch_panel = self._get_patch_panel_for_card(session, card)
                destination_bucket = patch_panel.pipe_bindings[output_pipe].bucket
                self._move_card_row(
                    session,
                    card=card,
                    to_bucket=destination_bucket,
                    actor_id=validator_id,
                    reason="validator_output",
                )
                event_payload["output_pipe"] = output_pipe
                event_payload["destination_bucket"] = destination_bucket

            event = CardEvent(
                card_id=card.id,
                event_type="card_validated",
                actor_id=validator_id,
                payload=event_payload,
            )
            self._insert_event(session, event)
            self._store_idempotency(session, idempotency_key, "card.validate", f"event:{event.id}")
            return event

    def move_card(
        self,
        *,
        card_id: UUID,
        to_bucket: str,
        actor_id: str | None = None,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> Card:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_card(session, UUID(cached.removeprefix("card:")))

            card = self._get_card(session, card_id)
            patch_panel = self._get_patch_panel_for_card(session, card)
            ensure_bucket_exists(patch_panel, to_bucket)
            moved = self._move_card_row(
                session,
                card=card,
                to_bucket=to_bucket,
                actor_id=actor_id,
                reason=reason,
            )
            self._store_idempotency(session, idempotency_key, "card.move", f"card:{card.id}")
            return moved

    def card_history(self, card_id: UUID) -> list[CardEvent]:
        with Session(self.engine) as session:
            self._get_card(session, card_id)
            rows = session.execute(
                select(card_events)
                .where(card_events.c.card_id == card_id)
                .order_by(card_events.c.occurred_at, card_events.c.id)
            ).all()
        return [_event_from_row(row._mapping) for row in rows]

    def record_event(
        self,
        *,
        card_id: UUID,
        event_type: str,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> CardEvent:
        with Session(self.engine) as session, session.begin():
            cached = self._get_idempotency(session, idempotency_key)
            if cached:
                return self._get_event(session, UUID(cached.removeprefix("event:")))

            self._get_card(session, card_id)
            event = CardEvent(
                card_id=card_id,
                event_type=event_type,
                actor_id=actor_id,
                payload=payload or {},
            )
            self._insert_event(session, event)
            self._store_idempotency(session, idempotency_key, "event.record", f"event:{event.id}")
            return event

    def _move_card_row(
        self,
        session: Session,
        *,
        card: Card,
        to_bucket: str,
        actor_id: str | None,
        reason: str | None,
        emit_event: bool = True,
    ) -> Card:
        now = datetime.now(UTC)
        session.execute(
            card_locations.update()
            .where(
                card_locations.c.card_id == card.id,
                card_locations.c.status == "active",
            )
            .values(status="exited", exited_at=now)
        )
        session.execute(
            card_locations.insert().values(
                id=uuid4(),
                card_id=card.id,
                bucket=to_bucket,
                status="active",
                entered_at=now,
                accepted_at=now,
                exited_at=None,
            )
        )
        session.execute(
            cards.update().where(cards.c.id == card.id).values(current_bucket=to_bucket)
        )
        if emit_event:
            event = CardEvent(
                card_id=card.id,
                event_type="card_moved",
                actor_id=actor_id,
                payload={
                    "from_bucket": card.current_bucket,
                    "to_bucket": to_bucket,
                    "reason": reason,
                },
            )
            self._insert_event(session, event)
        return card.model_copy(update={"current_bucket": to_bucket})

    def _insert_event(self, session: Session, event: CardEvent) -> None:
        session.execute(
            card_events.insert().values(
                id=event.id,
                card_id=event.card_id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                payload=event.payload,
                occurred_at=event.occurred_at,
            )
        )

    def _get_card(self, session: Session, card_id: UUID) -> Card:
        row = session.execute(select(cards).where(cards.c.id == card_id)).first()
        if row is None:
            raise NotFoundError(f"card '{card_id}' does not exist")
        return _card_from_row(row._mapping)

    def _get_event(self, session: Session, event_id: UUID) -> CardEvent:
        row = session.execute(select(card_events).where(card_events.c.id == event_id)).first()
        if row is None:
            raise NotFoundError(f"event '{event_id}' does not exist")
        return _event_from_row(row._mapping)

    def _get_lease(self, session: Session, lease_id: UUID) -> Lease:
        row = session.execute(select(leases).where(leases.c.id == lease_id)).first()
        if row is None:
            raise NotFoundError(f"lease '{lease_id}' does not exist")
        return self._lease_from_row(row._mapping)

    def _lease_from_row(self, row: Any) -> Lease:
        return Lease(
            id=row["id"],
            card_id=row["card_id"],
            node_id=row["node_id"],
            worker_id=row["worker_id"],
            input_pipe=row["input_pipe"],
            claimed_at=row["claimed_at"],
            expires_at=row["expires_at"],
            released_at=row["released_at"],
        )

    def _get_artifacts(
        self,
        session: Session,
        artifact_ids: list[UUID],
    ) -> list[ArtifactReference]:
        if not artifact_ids:
            return []
        rows = session.execute(select(artifacts).where(artifacts.c.id.in_(artifact_ids))).all()
        by_id = {
            row._mapping["id"]: _artifact_reference_from_row(row._mapping)
            for row in rows
        }
        missing = [artifact_id for artifact_id in artifact_ids if artifact_id not in by_id]
        if missing:
            raise NotFoundError(f"artifact '{missing[0]}' does not exist")
        return [by_id[artifact_id] for artifact_id in artifact_ids]

    def _get_active_patch_panel(self, session: Session, patch_panel_id: str) -> PatchPanel:
        row = session.execute(
            select(patch_panels.c.definition)
            .join(
                workflow_versions,
                (workflow_versions.c.patch_panel_id == patch_panels.c.id)
                & (workflow_versions.c.version == patch_panels.c.version),
            )
            .where(patch_panels.c.id == patch_panel_id, workflow_versions.c.active.is_(True))
        ).first()
        if row is None:
            raise NotFoundError(f"Patch Panel '{patch_panel_id}' is not registered")
        return PatchPanel.model_validate(row.definition)

    def _single_patch_panel(self, session: Session) -> PatchPanel:
        rows = session.execute(select(patch_panels.c.definition)).all()
        if not rows:
            raise NotFoundError("no Patch Panels are registered")
        if len(rows) > 1:
            raise ConflictError(
                "operation requires an explicit Patch Panel when multiple are registered"
            )
        return PatchPanel.model_validate(rows[0].definition)

    def _get_patch_panel_for_card(self, session: Session, card: Card) -> PatchPanel:
        patch_panel_id, version = card.workflow_version.split(":", maxsplit=1)
        row = session.execute(
            select(patch_panels.c.definition).where(
                patch_panels.c.id == patch_panel_id,
                patch_panels.c.version == version,
            )
        ).first()
        if row is None:
            raise NotFoundError(f"Patch Panel '{card.workflow_version}' is not registered")
        return PatchPanel.model_validate(row.definition)

    def _get_idempotency(self, session: Session, key: str | None) -> str | None:
        if not key:
            return None
        row = session.execute(
            select(idempotency_records.c.response_ref).where(idempotency_records.c.key == key)
        ).first()
        return str(row.response_ref) if row else None

    def _store_idempotency(
        self,
        session: Session,
        key: str | None,
        operation: str,
        response_ref: str,
    ) -> None:
        if not key:
            return
        try:
            session.execute(
                idempotency_records.insert().values(
                    key=key,
                    operation=operation,
                    response_ref=response_ref,
                    created_at=datetime.now(UTC),
                )
            )
        except IntegrityError as exc:
            raise ConflictError(f"idempotency key '{key}' already exists") from exc

def _workflow_version_id(patch_panel: PatchPanel) -> str:
    return f"{patch_panel.id}:{patch_panel.version}"


def _card_from_row(row: Any) -> Card:
    return Card(
        id=row["id"],
        workflow_version=row["workflow_version"],
        current_bucket=row["current_bucket"],
        payload=row["payload"],
        metadata=row["card_metadata"],
        created_at=row["created_at"],
    )


def _event_from_row(row: Any) -> CardEvent:
    return CardEvent(
        id=row["id"],
        card_id=row["card_id"],
        event_type=row["event_type"],
        actor_id=row["actor_id"],
        payload=row["payload"],
        occurred_at=row["occurred_at"],
    )


def _artifact_reference_from_row(row: Any) -> ArtifactReference:
    return ArtifactReference(
        id=row["id"],
        card_id=row["card_id"],
        event_id=row["event_id"],
        storage_ref=row["storage_ref"],
        content_hash=row["content_hash"],
        content_type=row["content_type"],
        size_bytes=row["size_bytes"],
        metadata=row["artifact_metadata"],
        created_at=row["created_at"],
    )
