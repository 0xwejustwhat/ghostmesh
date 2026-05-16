from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ghostmesh.domain import (
    ArtifactReference,
    Card,
    CardEvent,
    NodeDefinition,
    NodeType,
    PatchPanel,
)
from ghostmesh.runtime import CardRuntime
from ghostmesh.runtime.errors import InvalidOperationError, NotFoundError


class WorkerExecutionInput(BaseModel):
    input_pipe: str
    output_pipe: str
    worker_id: str
    artifact_refs: list[ArtifactReference]
    lease_seconds: int = 300
    idempotency_key: str | None = None


class ValidatorExecutionInput(BaseModel):
    card_id: UUID
    validator_id: str
    selected_exit: str | None = None
    accepted: bool | None = None
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SinkResult:
    event: CardEvent
    external_reference: str | None


class NodeExecutor:
    """MVP node execution layer composed from runtime primitives."""

    def __init__(self, *, patch_panel: PatchPanel, runtime: CardRuntime) -> None:
        self.patch_panel = patch_panel
        self.runtime = runtime

    def execute_source(
        self,
        *,
        source_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Card:
        node = self._node(source_id, NodeType.SOURCE)
        card = self.runtime.create_card(
            patch_panel_id=self.patch_panel.id,
            payload=payload,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )
        self.runtime.record_event(
            card_id=card.id,
            event_type="source_executed",
            actor_id=node.id,
            payload={"source_id": node.id},
            idempotency_key=f"{idempotency_key}:source" if idempotency_key else None,
        )
        return card

    def execute_worker(self, request: WorkerExecutionInput) -> list[ArtifactReference]:
        node_id = self._node_for_pipe(request.input_pipe, NodeType.WORKER).id
        lease = self.runtime.claim_card(
            input_pipe=request.input_pipe,
            worker_id=request.worker_id,
            lease_seconds=request.lease_seconds,
            idempotency_key=f"{request.idempotency_key}:claim" if request.idempotency_key else None,
        )
        artifact_refs = self.runtime.submit_artifact(
            lease_id=lease.id,
            output_pipe=request.output_pipe,
            artifact_refs=request.artifact_refs,
            idempotency_key=(
                f"{request.idempotency_key}:submit" if request.idempotency_key else None
            ),
        )
        if not artifact_refs:
            raise InvalidOperationError("worker execution produced no artifact references")
        event = self.runtime.card_history(lease.card_id)[-1]
        event_node_id = self.patch_panel.pipe_bindings[request.output_pipe].node
        if event_node_id != node_id:
            raise InvalidOperationError(
                f"worker pipe '{request.input_pipe}' resolved to '{node_id}' but output pipe "
                f"was bound to '{event_node_id}'"
            )
        if event.event_type != "artifact_submitted":
            raise InvalidOperationError("worker execution did not submit artifacts")
        return artifact_refs

    def execute_validator(self, request: ValidatorExecutionInput) -> CardEvent:
        node = self._node(request.validator_id, NodeType.VALIDATOR)
        selected_exit = request.selected_exit
        if selected_exit is None and self._requires_selected_exit(node):
            raise InvalidOperationError(
                f"routing validator '{node.id}' requires selected_exit"
            )
        if selected_exit is not None:
            self._ensure_validator_exit(node, selected_exit)
        accepted = self._validator_accepted(node, request)
        return self.runtime.validate_card(
            card_id=request.card_id,
            validator_id=node.id,
            accepted=accepted,
            reason=request.reason,
            output_pipe=selected_exit,
            idempotency_key=request.idempotency_key,
        )

    def execute_sink(
        self,
        *,
        card_id: UUID,
        sink_id: str,
        external_reference: str | None = None,
        idempotency_key: str | None = None,
    ) -> SinkResult:
        node = self._node(sink_id, NodeType.SINK)
        card = self.runtime.get_card(card_id)
        if card.metadata.get("shadow") and not node.config.get("allow_shadow_egress", False):
            raise InvalidOperationError("shadow cards cannot execute production sinks")
        event = self.runtime.record_event(
            card_id=card_id,
            event_type="sink_executed",
            actor_id=node.id,
            payload={
                "sink_id": node.id,
                "external_reference": external_reference,
                "egress_contract": node.config.get("egress_contract"),
                "egress_idempotency": node.config.get("egress_idempotency"),
            },
            idempotency_key=idempotency_key,
        )
        return SinkResult(event=event, external_reference=external_reference)

    def _node(self, node_id: str, expected_type: NodeType) -> NodeDefinition:
        for node in self.patch_panel.nodes:
            if node.id == node_id:
                if node.type != expected_type:
                    raise InvalidOperationError(
                        f"node '{node_id}' is '{node.type}', not '{expected_type}'"
                    )
                return node
        raise NotFoundError(f"node '{node_id}' does not exist")

    def _node_for_pipe(self, pipe: str, expected_type: NodeType) -> NodeDefinition:
        binding = self.patch_panel.pipe_bindings.get(pipe)
        if binding is None or binding.node is None:
            raise NotFoundError(f"pipe '{pipe}' is not bound to a node")
        return self._node(binding.node, expected_type)

    def _ensure_validator_exit(self, node: NodeDefinition, selected_exit: str) -> None:
        if selected_exit not in node.output_pipes:
            raise InvalidOperationError(
                f"exit pipe '{selected_exit}' is not declared by validator '{node.id}'"
            )
        binding = self.patch_panel.pipe_bindings.get(selected_exit)
        if binding is None:
            raise InvalidOperationError(
                f"selected exit pipe '{selected_exit}' is missing a Patch Panel binding"
            )
        if binding.node != node.id or binding.direction != "output":
            raise InvalidOperationError(
                f"selected exit pipe '{selected_exit}' is not an output binding for validator "
                f"'{node.id}'"
            )

    def _requires_selected_exit(self, node: NodeDefinition) -> bool:
        return node.validator_kind == "routing" or len(node.output_pipes) > 1

    def _validator_accepted(self, node: NodeDefinition, request: ValidatorExecutionInput) -> bool:
        if request.accepted is not None:
            return request.accepted
        if request.selected_exit is None:
            raise InvalidOperationError(
                f"validator '{node.id}' requires either accepted or selected_exit"
            )
        accept_exits = node.config.get("accept_exits")
        if isinstance(accept_exits, list):
            return request.selected_exit in accept_exits
        return True
