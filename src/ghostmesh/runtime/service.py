from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from ghostmesh.artifacts import validate_artifact_references
from ghostmesh.domain import ArtifactReference, Card, CardEvent, Lease, NodeType, PatchPanel
from ghostmesh.patchpanel import PatchPanelValidator
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError, NotFoundError


class CardRuntime(Protocol):
    def register_patch_panel(self, patch_panel: PatchPanel) -> PatchPanel: ...

    def list_patch_panels(self) -> list[PatchPanel]: ...

    def create_card(
        self,
        *,
        patch_panel_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Card: ...

    def list_cards(self) -> list[Card]: ...

    def get_card(self, card_id: UUID) -> Card: ...

    def get_lease(self, lease_id: UUID) -> Lease: ...

    def list_leases(self) -> list[Lease]: ...

    def claim_card(
        self,
        *,
        input_pipe: str,
        worker_id: str,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> Lease: ...

    def submit_artifact(
        self,
        *,
        lease_id: UUID,
        output_pipe: str,
        artifact_refs: list[ArtifactReference],
        idempotency_key: str | None = None,
    ) -> list[ArtifactReference]: ...

    def renew_lease(
        self,
        *,
        lease_id: UUID,
        lease_seconds: int = 300,
        idempotency_key: str | None = None,
    ) -> Lease: ...

    def release_lease(
        self,
        *,
        lease_id: UUID,
        actor_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> Lease: ...

    def expire_leases(self) -> list[Lease]: ...

    def validate_card(
        self,
        *,
        card_id: UUID,
        validator_id: str,
        accepted: bool,
        reason: str | None = None,
        output_pipe: str | None = None,
        idempotency_key: str | None = None,
    ) -> CardEvent: ...

    def move_card(
        self,
        *,
        card_id: UUID,
        to_bucket: str,
        actor_id: str | None = None,
        reason: str | None = None,
        idempotency_key: str | None = None,
    ) -> Card: ...

    def card_history(self, card_id: UUID) -> list[CardEvent]: ...

    def record_event(
        self,
        *,
        card_id: UUID,
        event_type: str,
        actor_id: str | None = None,
        payload: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> CardEvent: ...


def validate_patch_panel(patch_panel: PatchPanel) -> PatchPanel:
    PatchPanelValidator().validate(patch_panel)
    return patch_panel


def resolve_initial_bucket(patch_panel: PatchPanel) -> str:
    source = next((node for node in patch_panel.nodes if node.type == NodeType.SOURCE), None)
    if source is None:
        raise InvalidOperationError("Patch Panel has no source node")
    if not source.output_pipes:
        raise InvalidOperationError(f"source node '{source.id}' has no output pipe")

    binding = patch_panel.pipe_bindings.get(source.output_pipes[0])
    if binding is None:
        raise InvalidOperationError(f"source pipe '{source.output_pipes[0]}' is not bound")
    return binding.bucket


def resolve_pipe_bucket(patch_panel: PatchPanel, pipe: str, direction: str) -> tuple[str, str]:
    binding = patch_panel.pipe_bindings.get(pipe)
    if binding is None:
        raise InvalidOperationError(f"pipe '{pipe}' is not bound")
    if binding.direction and binding.direction != direction:
        raise InvalidOperationError(
            f"pipe '{pipe}' is configured as '{binding.direction}', not '{direction}'"
        )

    node_id = binding.node or _find_node_for_pipe(patch_panel, pipe, direction)
    return binding.bucket, node_id


def ensure_bucket_exists(patch_panel: PatchPanel, bucket_id: str) -> None:
    if bucket_id not in {bucket.id for bucket in patch_panel.buckets}:
        raise InvalidOperationError(f"bucket '{bucket_id}' is not declared")


def ensure_active_lease(lease: Lease) -> None:
    if lease.released_at is not None:
        raise ConflictError(f"lease '{lease.id}' has already been released")
    expires_at = lease.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        raise ConflictError(f"lease '{lease.id}' has expired")


def new_lease(*, card: Card, node_id: str, worker_id: str, input_pipe: str, seconds: int) -> Lease:
    return Lease(
        card_id=card.id,
        node_id=node_id,
        worker_id=worker_id,
        input_pipe=input_pipe,
        expires_at=datetime.now(UTC) + timedelta(seconds=seconds),
    )


def ensure_artifacts_accepted(
    patch_panel: PatchPanel,
    *,
    destination_bucket_id: str,
    artifact_refs: list[ArtifactReference],
) -> None:
    bucket = next(
        (bucket for bucket in patch_panel.buckets if bucket.id == destination_bucket_id),
        None,
    )
    if bucket is None:
        raise InvalidOperationError(f"bucket '{destination_bucket_id}' is not declared")
    contract_id = bucket.acceptance_contract
    if contract_id is None:
        return
    contract = next(
        (contract for contract in patch_panel.acceptance_contracts if contract.id == contract_id),
        None,
    )
    if contract is None:
        raise InvalidOperationError(
            f"bucket '{destination_bucket_id}' references unknown acceptance contract "
            f"'{contract_id}'"
        )
    validate_artifact_references(artifact_refs, contract)


def ensure_artifact_refs_belong_to_card(
    *,
    card_id: UUID,
    artifact_refs: list[ArtifactReference],
) -> None:
    if not artifact_refs:
        raise InvalidOperationError("submit requires at least one artifact reference")
    for artifact_ref in artifact_refs:
        if artifact_ref.card_id != card_id:
            raise InvalidOperationError(
                f"artifact '{artifact_ref.id}' belongs to card '{artifact_ref.card_id}', "
                f"not '{card_id}'"
            )


def _find_node_for_pipe(patch_panel: PatchPanel, pipe: str, direction: str) -> str:
    for node in patch_panel.nodes:
        pipes = node.input_pipes if direction == "input" else node.output_pipes
        if pipe in pipes:
            return node.id
    raise NotFoundError(f"pipe '{pipe}' is not declared by any node")
