from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from ghostmesh.domain import Artifact, Card, CardEvent, Lease, PatchPanel
from ghostmesh.runtime.errors import ConflictError, NotFoundError
from ghostmesh.runtime.service import (
    ensure_active_lease,
    ensure_bucket_exists,
    new_lease,
    resolve_initial_bucket,
    resolve_pipe_bucket,
    validate_patch_panel,
)


class InMemoryCardRuntime:
    """Small deterministic runtime used by tests and the early API shell."""

    def __init__(self) -> None:
        self._patch_panels: dict[str, PatchPanel] = {}
        self._cards: dict[UUID, Card] = {}
        self._leases: dict[UUID, Lease] = {}
        self._artifacts: dict[UUID, Artifact] = {}
        self._events: dict[UUID, list[CardEvent]] = {}
        self._idempotency: dict[str, object] = {}

    def register_patch_panel(self, patch_panel: PatchPanel) -> PatchPanel:
        validate_patch_panel(patch_panel)
        self._patch_panels[patch_panel.id] = patch_panel
        return patch_panel

    def list_patch_panels(self) -> list[PatchPanel]:
        return list(self._patch_panels.values())

    def create_card(
        self,
        *,
        patch_panel_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Card:
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, Card)

        patch_panel = self._get_patch_panel(patch_panel_id)
        card = Card(
            workflow_version=f"{patch_panel.id}:{patch_panel.version}",
            current_bucket=resolve_initial_bucket(patch_panel),
            payload=payload,
            metadata=metadata or {},
        )
        self._cards[card.id] = card
        self._record_event(
            CardEvent(
                card_id=card.id,
                event_type="card_created",
                payload={
                    "patch_panel_id": patch_panel.id,
                    "version": patch_panel.version,
                    "bucket": card.current_bucket,
                },
            )
        )
        self._store_idempotent(idempotency_key, card)
        return card

    def list_cards(self) -> list[Card]:
        return list(self._cards.values())

    def get_card(self, card_id: UUID) -> Card:
        return self._get_card(card_id)

    def get_lease(self, lease_id: UUID) -> Lease:
        return self._get_lease(lease_id)

    def claim_card(
        self,
        *,
        input_pipe: str,
        worker_id: str,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> Lease:
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, Lease)

        patch_panel = self._single_patch_panel()
        bucket, node_id = resolve_pipe_bucket(patch_panel, input_pipe, "input")
        card = next(
            (
                card
                for card in self._cards.values()
                if card.current_bucket == bucket and not self._has_active_lease(card.id)
            ),
            None,
        )
        if card is None:
            raise NotFoundError(f"no claimable cards in bucket '{bucket}'")

        lease = new_lease(
            card=card,
            node_id=node_id,
            worker_id=worker_id,
            input_pipe=input_pipe,
            seconds=lease_seconds,
        )
        self._leases[lease.id] = lease
        self._record_event(
            CardEvent(
                card_id=card.id,
                event_type="card_claimed",
                actor_id=worker_id,
                payload={"lease_id": str(lease.id), "input_pipe": input_pipe},
            )
        )
        self._store_idempotent(idempotency_key, lease)
        return lease

    def submit_artifact(
        self,
        *,
        lease_id: UUID,
        output_pipe: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> Artifact:
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, Artifact)

        lease = self._get_lease(lease_id)
        ensure_active_lease(lease)
        card = self._get_card(lease.card_id)
        patch_panel = self._single_patch_panel()
        destination_bucket, node_id = resolve_pipe_bucket(patch_panel, output_pipe, "output")

        if node_id != lease.node_id:
            raise ConflictError(
                f"lease node '{lease.node_id}' cannot submit through node '{node_id}'"
            )

        artifact = Artifact(
            card_id=card.id,
            node_id=node_id,
            worker_id=lease.worker_id,
            payload=payload,
        )
        self._artifacts[artifact.id] = artifact

        updated_card = card.model_copy(update={"current_bucket": destination_bucket})
        self._cards[card.id] = updated_card
        released_lease = lease.model_copy(update={"released_at": datetime.now(UTC)})
        self._leases[lease.id] = released_lease

        self._record_event(
            CardEvent(
                card_id=card.id,
                event_type="artifact_submitted",
                actor_id=lease.worker_id,
                payload={
                    "artifact_id": str(artifact.id),
                    "lease_id": str(lease.id),
                    "output_pipe": output_pipe,
                    "destination_bucket": destination_bucket,
                },
            )
        )
        self._store_idempotent(idempotency_key, artifact)
        return artifact

    def renew_lease(
        self,
        *,
        lease_id: UUID,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> Lease:
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, Lease)

        lease = self._get_lease(lease_id)
        ensure_active_lease(lease)
        renewed = lease.model_copy(
            update={"expires_at": datetime.now(UTC) + timedelta(seconds=lease_seconds)}
        )
        self._leases[lease.id] = renewed
        self._record_event(
            CardEvent(
                card_id=lease.card_id,
                event_type="lease_renewed",
                actor_id=lease.worker_id,
                payload={"lease_id": str(lease.id), "expires_at": renewed.expires_at.isoformat()},
            )
        )
        self._store_idempotent(idempotency_key, renewed)
        return renewed

    def release_lease(
        self,
        *,
        lease_id: UUID,
        actor_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Lease:
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, Lease)

        lease = self._get_lease(lease_id)
        if lease.released_at is not None:
            return lease
        released = lease.model_copy(update={"released_at": datetime.now(UTC)})
        self._leases[lease.id] = released
        self._record_event(
            CardEvent(
                card_id=lease.card_id,
                event_type="lease_released",
                actor_id=actor_id or lease.worker_id,
                payload={"lease_id": str(lease.id)},
            )
        )
        self._store_idempotent(idempotency_key, released)
        return released

    def expire_leases(self) -> list[Lease]:
        now = datetime.now(UTC)
        expired: list[Lease] = []
        for lease in list(self._leases.values()):
            expires_at = lease.expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=UTC)
            if lease.released_at is None and expires_at <= now:
                released = lease.model_copy(update={"released_at": now})
                self._leases[lease.id] = released
                expired.append(released)
                self._record_event(
                    CardEvent(
                        card_id=lease.card_id,
                        event_type="lease_expired",
                        actor_id=lease.worker_id,
                        payload={"lease_id": str(lease.id)},
                    )
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
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, CardEvent)

        card = self._get_card(card_id)
        payload: dict[str, Any] = {"accepted": accepted, "reason": reason}
        if output_pipe:
            patch_panel = self._single_patch_panel()
            destination_bucket, _node_id = resolve_pipe_bucket(patch_panel, output_pipe, "output")
            self._cards[card.id] = card.model_copy(update={"current_bucket": destination_bucket})
            payload["output_pipe"] = output_pipe
            payload["destination_bucket"] = destination_bucket

        event = CardEvent(
            card_id=card.id,
            event_type="card_validated",
            actor_id=validator_id,
            payload=payload,
        )
        self._record_event(event)
        self._store_idempotent(idempotency_key, event)
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
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, Card)

        card = self._get_card(card_id)
        patch_panel = self._single_patch_panel()
        ensure_bucket_exists(patch_panel, to_bucket)
        moved = card.model_copy(update={"current_bucket": to_bucket})
        self._cards[card.id] = moved
        self._record_event(
            CardEvent(
                card_id=card.id,
                event_type="card_moved",
                actor_id=actor_id,
                payload={
                    "from_bucket": card.current_bucket,
                    "to_bucket": to_bucket,
                    "reason": reason,
                },
            )
        )
        self._store_idempotent(idempotency_key, moved)
        return moved

    def card_history(self, card_id: UUID) -> list[CardEvent]:
        self._get_card(card_id)
        return list(self._events.get(card_id, []))

    def record_event(
        self,
        *,
        card_id: UUID,
        event_type: str,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> CardEvent:
        if cached := self._get_idempotent(idempotency_key):
            return _typed(cached, CardEvent)

        self._get_card(card_id)
        event = CardEvent(
            card_id=card_id,
            event_type=event_type,
            actor_id=actor_id,
            payload=payload or {},
        )
        self._record_event(event)
        self._store_idempotent(idempotency_key, event)
        return event

    def _record_event(self, event: CardEvent) -> None:
        self._events.setdefault(event.card_id, []).append(event)

    def _has_active_lease(self, card_id: UUID) -> bool:
        now = datetime.now(UTC)
        return any(
            lease.card_id == card_id and lease.released_at is None and lease.expires_at > now
            for lease in self._leases.values()
        )

    def _get_patch_panel(self, patch_panel_id: str) -> PatchPanel:
        try:
            return self._patch_panels[patch_panel_id]
        except KeyError as exc:
            raise NotFoundError(f"Patch Panel '{patch_panel_id}' is not registered") from exc

    def _single_patch_panel(self) -> PatchPanel:
        if not self._patch_panels:
            raise NotFoundError("no Patch Panels are registered")
        if len(self._patch_panels) > 1:
            raise ConflictError(
                "operation requires an explicit Patch Panel when multiple are registered"
            )
        return next(iter(self._patch_panels.values()))

    def _get_card(self, card_id: UUID) -> Card:
        try:
            return self._cards[card_id]
        except KeyError as exc:
            raise NotFoundError(f"card '{card_id}' does not exist") from exc

    def _get_lease(self, lease_id: UUID) -> Lease:
        try:
            return self._leases[lease_id]
        except KeyError as exc:
            raise NotFoundError(f"lease '{lease_id}' does not exist") from exc

    def _get_idempotent(self, key: str | None) -> object | None:
        return self._idempotency.get(key) if key else None

    def _store_idempotent(self, key: str | None, value: object) -> None:
        if key:
            self._idempotency[key] = value


def _typed(value: object, expected_type: type[Any]) -> Any:
    if not isinstance(value, expected_type):
        raise ConflictError("idempotency key was already used for a different operation")
    return value
