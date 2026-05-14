from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ghostmesh.domain import Artifact, Card, CardEvent, NodeDefinition, NodeType, PatchPanel
from ghostmesh.runtime import CardRuntime
from ghostmesh.runtime.errors import InvalidOperationError, NotFoundError


class WorkerExecutionInput(BaseModel):
    input_pipe: str
    output_pipe: str
    worker_id: str
    payload: dict[str, Any]
    lease_seconds: int = 300
    idempotency_key: str | None = None


class HumanValidationInput(BaseModel):
    card_id: UUID
    validator_id: str
    accepted: bool
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class JunctionDecision:
    card: Card
    selected_pipe: str
    selected_bucket: str
    accepted: bool


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

    def execute_worker(self, request: WorkerExecutionInput) -> Artifact:
        node_id = self._node_for_pipe(request.input_pipe, NodeType.WORKER).id
        lease = self.runtime.claim_card(
            input_pipe=request.input_pipe,
            worker_id=request.worker_id,
            lease_seconds=request.lease_seconds,
            idempotency_key=f"{request.idempotency_key}:claim" if request.idempotency_key else None,
        )
        artifact = self.runtime.submit_artifact(
            lease_id=lease.id,
            output_pipe=request.output_pipe,
            payload=request.payload,
            idempotency_key=(
                f"{request.idempotency_key}:submit" if request.idempotency_key else None
            ),
        )
        if artifact.node_id != node_id:
            raise InvalidOperationError(
                f"worker pipe '{request.input_pipe}' resolved to '{node_id}' but artifact "
                f"was submitted by '{artifact.node_id}'"
            )
        return artifact

    def execute_human_validator(self, request: HumanValidationInput) -> CardEvent:
        node = self._node(request.validator_id, NodeType.VALIDATOR)
        return self.runtime.validate_card(
            card_id=request.card_id,
            validator_id=node.id,
            accepted=request.accepted,
            reason=request.reason,
            output_pipe=None,
            idempotency_key=request.idempotency_key,
        )

    def execute_junction(
        self,
        *,
        card_id: UUID,
        junction_id: str,
        idempotency_key: str | None = None,
    ) -> JunctionDecision:
        node = self._node(junction_id, NodeType.JUNCTION)
        validation = self._latest_validation(card_id)
        accepted = bool(validation.payload.get("accepted"))
        selected_pipe = self._select_junction_pipe(node, accepted)
        selected_bucket = self.patch_panel.pipe_bindings[selected_pipe].bucket
        moved = self.runtime.move_card(
            card_id=card_id,
            to_bucket=selected_bucket,
            actor_id=node.id,
            reason="junction_route",
            idempotency_key=idempotency_key,
        )
        self.runtime.record_event(
            card_id=card_id,
            event_type="junction_routed",
            actor_id=node.id,
            payload={
                "junction_id": node.id,
                "selected_pipe": selected_pipe,
                "selected_bucket": selected_bucket,
                "accepted": accepted,
            },
            idempotency_key=f"{idempotency_key}:junction" if idempotency_key else None,
        )
        return JunctionDecision(
            card=moved,
            selected_pipe=selected_pipe,
            selected_bucket=selected_bucket,
            accepted=accepted,
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

    def _latest_validation(self, card_id: UUID) -> CardEvent:
        for event in reversed(self.runtime.card_history(card_id)):
            if event.event_type == "card_validated":
                return event
        raise NotFoundError(f"card '{card_id}' has no validation event")

    def _select_junction_pipe(self, node: NodeDefinition, accepted: bool) -> str:
        routes = node.config.get("routes", {})
        route_key = "accepted" if accepted else "rejected"
        selected_pipe = routes.get(route_key)
        if not isinstance(selected_pipe, str):
            raise InvalidOperationError(
                f"junction '{node.id}' is missing route '{route_key}'"
            )
        if selected_pipe not in node.output_pipes:
            raise InvalidOperationError(
                f"junction '{node.id}' route '{route_key}' uses undeclared pipe "
                f"'{selected_pipe}'"
            )
        if selected_pipe not in self.patch_panel.pipe_bindings:
            raise InvalidOperationError(f"junction pipe '{selected_pipe}' is not bound")
        return selected_pipe
