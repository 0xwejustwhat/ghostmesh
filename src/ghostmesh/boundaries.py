from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ghostmesh.domain import Card, CardEvent, NodeDefinition, NodeType, PatchPanel
from ghostmesh.nodes import NodeExecutor, SinkResult
from ghostmesh.runtime import CardRuntime
from ghostmesh.runtime.errors import InvalidOperationError, NotFoundError


class BoundaryAuth(BaseModel):
    token: str | None = None
    tokens: list[str] = Field(default_factory=list)


class SourceBoundaryContract(BaseModel):
    adapter: str = "webhook"
    auth: BoundaryAuth | None = None
    payload_map: dict[str, str] = Field(default_factory=dict)
    metadata_map: dict[str, str] = Field(default_factory=dict)
    deduplication_key: str | None = None
    target_workflow_version: str | None = None


class SinkBoundaryContract(BaseModel):
    adapter: str = "webhook"
    auth: BoundaryAuth | None = None
    payload_map: dict[str, str] = Field(default_factory=dict)
    idempotency_key: str | None = None
    external_reference_path: str | None = None


class BoundarySourceRequest(BaseModel):
    patch_panel_id: str
    source_id: str
    external_payload: dict[str, Any]
    headers: dict[str, Any] = Field(default_factory=dict)
    actor_token: str | None = None


class BoundarySinkRequest(BaseModel):
    patch_panel_id: str
    sink_id: str
    card_id: UUID
    external_response: dict[str, Any] = Field(default_factory=dict)
    actor_token: str | None = None


@dataclass(frozen=True)
class SourceBoundaryResult:
    card: Card
    deduplication_key: str | None
    adapter: str


@dataclass(frozen=True)
class SinkBoundaryResult:
    event: CardEvent
    external_reference: str | None
    egress_idempotency_key: str | None
    adapter: str


class BoundaryAdapterService:
    """Controlled ingress and egress adapter layer for Source and Sink nodes."""

    def __init__(self, *, runtime: CardRuntime) -> None:
        self.runtime = runtime

    def execute_source(self, request: BoundarySourceRequest) -> SourceBoundaryResult:
        patch_panel = self._patch_panel(request.patch_panel_id)
        node = self._node(patch_panel, request.source_id, NodeType.SOURCE)
        contract = SourceBoundaryContract.model_validate(
            node.config.get("boundary_contract", node.config.get("ingress_contract", {}))
        )
        _ensure_authorized(contract.auth, request.actor_token)
        if (
            contract.target_workflow_version is not None
            and contract.target_workflow_version != f"{patch_panel.id}:{patch_panel.version}"
        ):
            raise InvalidOperationError(
                f"source '{node.id}' targets workflow '{contract.target_workflow_version}', "
                f"not '{patch_panel.id}:{patch_panel.version}'"
            )

        envelope = _envelope(request.external_payload, request.headers)
        payload = _map_payload(envelope, contract.payload_map) or request.external_payload
        metadata = _map_payload(envelope, contract.metadata_map)
        metadata.update(
            {
                "boundary_adapter": contract.adapter,
                "boundary_source": node.id,
            }
        )
        deduplication_key = (
            str(_extract_path(envelope, contract.deduplication_key))
            if contract.deduplication_key
            else None
        )
        if deduplication_key:
            metadata["deduplication_key"] = deduplication_key

        executor = NodeExecutor(patch_panel=patch_panel, runtime=self.runtime)
        card = executor.execute_source(
            source_id=node.id,
            payload=payload,
            metadata=metadata,
            idempotency_key=(
                f"boundary-source:{patch_panel.id}:{node.id}:{deduplication_key}"
                if deduplication_key
                else None
            ),
        )
        self.runtime.record_event(
            card_id=card.id,
            event_type="boundary_source_received",
            actor_id=node.id,
            payload={
                "adapter": contract.adapter,
                "source_id": node.id,
                "deduplication_key": deduplication_key,
                "headers": request.headers,
            },
            idempotency_key=(
                f"boundary-source:{patch_panel.id}:{node.id}:{deduplication_key}:event"
                if deduplication_key
                else None
            ),
        )
        return SourceBoundaryResult(
            card=card,
            deduplication_key=deduplication_key,
            adapter=contract.adapter,
        )

    def execute_sink(self, request: BoundarySinkRequest) -> SinkBoundaryResult:
        patch_panel = self._patch_panel(request.patch_panel_id)
        node = self._node(patch_panel, request.sink_id, NodeType.SINK)
        contract = SinkBoundaryContract.model_validate(
            node.config.get("boundary_contract", node.config.get("egress_contract", {}))
        )
        _ensure_authorized(contract.auth, request.actor_token)
        card = self.runtime.get_card(request.card_id)
        envelope = {
            "card": card.model_dump(mode="json"),
            "external_response": request.external_response,
        }
        external_payload = _map_payload(envelope, contract.payload_map)
        external_reference = None
        if contract.external_reference_path:
            external_reference = str(_extract_path(envelope, contract.external_reference_path))
        elif request.external_response.get("external_reference") is not None:
            external_reference = str(request.external_response["external_reference"])

        egress_idempotency_key = _render_template(
            contract.idempotency_key or "card_id + sink_id",
            card=card,
            sink_id=node.id,
            external_reference=external_reference,
        )
        executor = NodeExecutor(patch_panel=patch_panel, runtime=self.runtime)
        result: SinkResult = executor.execute_sink(
            card_id=card.id,
            sink_id=node.id,
            external_reference=external_reference,
            idempotency_key=f"boundary-sink:{patch_panel.id}:{node.id}:{egress_idempotency_key}",
        )
        self.runtime.record_event(
            card_id=card.id,
            event_type="boundary_sink_egressed",
            actor_id=node.id,
            payload={
                "adapter": contract.adapter,
                "sink_id": node.id,
                "external_payload": external_payload,
                "external_reference": result.external_reference,
                "egress_idempotency_key": egress_idempotency_key,
            },
            idempotency_key=(
                f"boundary-sink:{patch_panel.id}:{node.id}:{egress_idempotency_key}:event"
            ),
        )
        return SinkBoundaryResult(
            event=result.event,
            external_reference=result.external_reference,
            egress_idempotency_key=egress_idempotency_key,
            adapter=contract.adapter,
        )

    def _patch_panel(self, patch_panel_id: str) -> PatchPanel:
        for patch_panel in self.runtime.list_patch_panels():
            if patch_panel.id == patch_panel_id:
                return patch_panel
        raise NotFoundError(f"Patch Panel '{patch_panel_id}' is not registered")

    def _node(
        self,
        patch_panel: PatchPanel,
        node_id: str,
        expected_type: NodeType,
    ) -> NodeDefinition:
        for node in patch_panel.nodes:
            if node.id == node_id:
                if node.type != expected_type:
                    raise InvalidOperationError(
                        f"node '{node_id}' is '{node.type}', not '{expected_type}'"
                    )
                return node
        raise NotFoundError(f"node '{node_id}' does not exist")


def _ensure_authorized(auth: BoundaryAuth | None, actor_token: str | None) -> None:
    if auth is None:
        return
    allowed = set(auth.tokens)
    if auth.token:
        allowed.add(auth.token)
    if allowed and actor_token not in allowed:
        raise InvalidOperationError("boundary adapter authorization failed")


def _envelope(payload: dict[str, Any], headers: dict[str, Any]) -> dict[str, Any]:
    return {"payload": payload, "headers": headers}


def _map_payload(envelope: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    return {target: _extract_path(envelope, source) for target, source in mapping.items()}


def _extract_path(envelope: dict[str, Any], path: str | None) -> Any:
    if not path:
        return None
    value: Any = envelope
    for part in path.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
            continue
        raise InvalidOperationError(f"boundary mapping path '{path}' was not found")
    return value


def _render_template(
    template: str,
    *,
    card: Card,
    sink_id: str,
    external_reference: str | None,
) -> str:
    values = {
        "card_id": str(card.id),
        "sink_id": sink_id,
        "workflow_version": card.workflow_version,
        "external_reference": external_reference or "",
    }
    if template in values:
        return values[template]
    parts = [part.strip() for part in template.split("+")]
    if len(parts) > 1 and all(part in values for part in parts):
        return ":".join(values[part] for part in parts)
    return template.format(**values)
