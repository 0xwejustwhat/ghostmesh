from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ghostmesh.persistence.tables import cards, idempotency_records, leases
from ghostmesh.runtime.errors import ConflictError, NotFoundError


class PostgresLeaseStore:
    """Postgres-ready lease and idempotency helper used by the runtime later.

    The implementation uses SQLAlchemy Core and `SELECT ... FOR UPDATE` for claim
    contention. Tests can exercise it with another SQLAlchemy engine, but the
    intended production target is Postgres.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def acquire_lease(
        self,
        *,
        card_id: UUID,
        node_id: str,
        worker_id: str,
        input_pipe: str,
        lease_seconds: int,
        idempotency_key: str | None = None,
    ) -> UUID:
        with Session(self.engine) as session, session.begin():
            if idempotency_key:
                cached = self._get_idempotency(session, idempotency_key)
                if cached:
                    return UUID(cached)

            card_row = session.execute(
                select(cards.c.id).where(cards.c.id == card_id).with_for_update()
            ).first()
            if card_row is None:
                raise NotFoundError(f"card '{card_id}' does not exist")

            active_lease = session.execute(
                select(leases.c.id).where(
                    leases.c.card_id == card_id,
                    leases.c.released_at.is_(None),
                    leases.c.expires_at > datetime.now(UTC),
                )
            ).first()
            if active_lease is not None:
                raise ConflictError(f"card '{card_id}' already has an active lease")

            lease_id = uuid4()
            session.execute(
                leases.insert().values(
                    id=lease_id,
                    card_id=card_id,
                    node_id=node_id,
                    worker_id=worker_id,
                    input_pipe=input_pipe,
                    claimed_at=datetime.now(UTC),
                    expires_at=datetime.now(UTC) + timedelta(seconds=lease_seconds),
                    released_at=None,
                )
            )
            if idempotency_key:
                self._store_idempotency(session, idempotency_key, str(lease_id))
            return lease_id

    def release_lease(self, *, lease_id: UUID) -> None:
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                leases.update()
                .where(leases.c.id == lease_id, leases.c.released_at.is_(None))
                .values(released_at=datetime.now(UTC))
            )
            if result.rowcount == 0:
                raise NotFoundError(f"active lease '{lease_id}' does not exist")

    def _get_idempotency(self, session: Session, key: str) -> str | None:
        row = session.execute(
            select(idempotency_records.c.response_ref).where(idempotency_records.c.key == key)
        ).first()
        return str(row.response_ref) if row else None

    def _store_idempotency(self, session: Session, key: str, response_ref: str) -> None:
        try:
            session.execute(
                idempotency_records.insert().values(
                    key=key,
                    operation="lease.acquire",
                    response_ref=response_ref,
                    created_at=datetime.now(UTC),
                )
            )
        except IntegrityError as exc:
            raise ConflictError(f"idempotency key '{key}' already exists") from exc

