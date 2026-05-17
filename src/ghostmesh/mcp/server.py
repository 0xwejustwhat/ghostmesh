from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import FastAPI
from fastmcp.server import Context, FastMCP

from ghostmesh.auth import AuthorizationService
from ghostmesh.auth.dependencies import PARTICIPANT_HEADER
from ghostmesh.boundaries import BoundaryAdapterService, BoundarySinkRequest, BoundarySourceRequest
from ghostmesh.domain import ArtifactReference, PermissionName, Scope, ScopeType
from ghostmesh.nodes import NodeExecutor, ValidatorExecutionInput
from ghostmesh.registry import PatchPanelRegistry
from ghostmesh.runtime import CardRuntime

mcp = FastMCP("Ghost Mesh")


@dataclass
class MCPState:
    runtime: CardRuntime
    registry: PatchPanelRegistry
    authorization_enabled: bool
    authorization_service: AuthorizationService


_state: MCPState | None = None


def bind_app(app: FastAPI) -> None:
    """Bind the FastMCP tool layer to an initialized Ghost Mesh app."""
    global _state
    _state = MCPState(
        runtime=app.state.runtime,
        registry=app.state.registry,
        authorization_enabled=app.state.authorization_enabled,
        authorization_service=app.state.authorization_service,
    )


def mount_mcp_endpoints(app: FastAPI) -> None:
    """Mount native FastMCP SSE endpoints under /mcp on the FastAPI app."""
    bind_app(app)
    app.mount("/mcp", mcp.http_app(path="/sse", transport="sse"))


def run_stdio() -> None:
    """Run the bound MCP server over stdio."""
    mcp.run(transport="stdio")


@mcp.tool(name="ghostmesh.claim_card")
async def claim_card(
    worker_id: str,
    input_pipe: str,
    lease_seconds: int = 300,
    idempotency_key: str | None = None,
    participant_id: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Claim a Card lease from an input pipe."""
    state = _require_state()
    _authorize(
        state,
        ctx,
        PermissionName.CARD_CLAIM,
        Scope(type=ScopeType.BUCKET, id=input_pipe),
        participant_id=participant_id or worker_id,
        context={"input_pipe": input_pipe, "worker_id": worker_id},
    )
    lease = state.runtime.claim_card(
        input_pipe=input_pipe,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
        idempotency_key=idempotency_key,
    )
    return lease.model_dump(mode="json")


@mcp.tool(name="ghostmesh.submit_artifact")
async def submit_artifact(
    lease_id: str,
    output_pipe: str,
    artifact_refs: list[dict[str, Any]],
    idempotency_key: str | None = None,
    participant_id: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Submit artifact references for an active Card lease."""
    state = _require_state()
    lease_uuid = UUID(str(lease_id))
    lease = state.runtime.get_lease(lease_uuid)
    _authorize(
        state,
        ctx,
        PermissionName.CARD_SUBMIT_ARTIFACT,
        Scope(type=ScopeType.CARD, id=str(lease.card_id)),
        participant_id=participant_id or lease.worker_id,
        context={"lease_id": str(lease_uuid), "output_pipe": output_pipe},
    )
    refs = [ArtifactReference.model_validate(ref) for ref in artifact_refs]
    submitted = state.runtime.submit_artifact(
        lease_id=lease_uuid,
        output_pipe=output_pipe,
        artifact_refs=refs,
        idempotency_key=idempotency_key,
    )
    return {"artifact_refs": [ref.model_dump(mode="json") for ref in submitted]}


@mcp.tool(name="ghostmesh.submit_validator_decision")
async def submit_validator_decision(
    validator_id: str,
    card_id: str,
    patch_panel_id: str,
    accepted: bool | None = None,
    selected_exit: str | None = None,
    score: int | None = None,
    reason: str | None = None,
    idempotency_key: str | None = None,
    participant_id: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Record a validator decision and route through a declared exit pipe."""
    state = _require_state()
    card_uuid = UUID(str(card_id))
    _authorize(
        state,
        ctx,
        PermissionName.VALIDATION_SUBMIT,
        Scope(type=ScopeType.CARD, id=str(card_uuid)),
        participant_id=participant_id or validator_id,
        context={"patch_panel_id": patch_panel_id, "validator_id": validator_id},
    )
    executor = NodeExecutor(
        patch_panel=_patch_panel(state.runtime, patch_panel_id),
        runtime=state.runtime,
        registry=state.registry,
        authorization_repository=state.authorization_service.repository,
    )
    event = executor.execute_validator(
        ValidatorExecutionInput(
            card_id=card_uuid,
            validator_id=validator_id,
            accepted=accepted,
            selected_exit=selected_exit,
            score=score,
            reason=reason,
            idempotency_key=idempotency_key,
        )
    )
    return event.model_dump(mode="json")


@mcp.tool(name="ghostmesh.boundary_source")
async def boundary_source(
    patch_panel_id: str,
    source_id: str,
    external_payload: dict[str, Any],
    headers: dict[str, Any] | None = None,
    actor_token: str | None = None,
    participant_id: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Execute an authorized Source boundary adapter."""
    state = _require_state()
    _authorize(
        state,
        ctx,
        PermissionName.BOUNDARY_SOURCE_INGRESS,
        Scope(type=ScopeType.PATCH_PANEL, id=patch_panel_id),
        participant_id=participant_id,
        context={"patch_panel_id": patch_panel_id, "source_id": source_id},
    )
    request = BoundarySourceRequest.model_validate(
        {
            "patch_panel_id": patch_panel_id,
            "source_id": source_id,
            "external_payload": external_payload,
            "headers": headers or {},
            "actor_token": actor_token,
        }
    )
    result = BoundaryAdapterService(runtime=state.runtime).execute_source(request)
    return {
        "card": result.card.model_dump(mode="json"),
        "deduplication_key": result.deduplication_key,
        "adapter": result.adapter,
    }


@mcp.tool(name="ghostmesh.boundary_sink")
async def boundary_sink(
    patch_panel_id: str,
    sink_id: str,
    card_id: str,
    external_response: dict[str, Any] | None = None,
    actor_token: str | None = None,
    participant_id: str | None = None,
    ctx: Context = None,
) -> dict[str, Any]:
    """Execute an authorized Sink boundary adapter."""
    state = _require_state()
    _authorize(
        state,
        ctx,
        PermissionName.BOUNDARY_SINK_EGRESS,
        Scope(type=ScopeType.PATCH_PANEL, id=patch_panel_id),
        participant_id=participant_id,
        context={"patch_panel_id": patch_panel_id, "sink_id": sink_id},
    )
    request = BoundarySinkRequest.model_validate(
        {
            "patch_panel_id": patch_panel_id,
            "sink_id": sink_id,
            "card_id": card_id,
            "external_response": external_response or {},
            "actor_token": actor_token,
        }
    )
    result = BoundaryAdapterService(runtime=state.runtime).execute_sink(request)
    return {
        "event": result.event.model_dump(mode="json"),
        "external_reference": result.external_reference,
        "egress_idempotency_key": result.egress_idempotency_key,
        "adapter": result.adapter,
    }


def _require_state() -> MCPState:
    if _state is None:
        raise RuntimeError("Ghost Mesh MCP server is not bound to application state")
    return _state


def _authorize(
    state: MCPState,
    ctx: Context | None,
    permission: PermissionName,
    scope: Scope,
    *,
    participant_id: str | None,
    context: dict[str, Any],
) -> str | None:
    if not state.authorization_enabled:
        return participant_id

    resolved = _participant_from_context(ctx) or participant_id
    if not resolved:
        raise PermissionError("missing Ghost Mesh participant")

    decision = state.authorization_service.authorize(
        participant_id=resolved,
        permission=permission,
        scope=scope,
        context=context,
    )
    if not decision.allowed:
        raise PermissionError(decision.reason)
    return resolved


def _participant_from_context(ctx: Context | None) -> str | None:
    if ctx is None:
        return None
    try:
        request_context = ctx.request_context
        request = request_context.request if request_context is not None else None
    except ValueError:
        request = None
    headers = getattr(request, "headers", None)
    if headers is not None:
        participant = headers.get(PARTICIPANT_HEADER)
        if participant:
            return participant
    try:
        request_context = ctx.request_context
        meta = request_context.meta if request_context is not None else None
    except ValueError:
        return None
    for name in ("ghostmesh_participant", "participant_id", "client_id"):
        value = getattr(meta, name, None) if meta is not None else None
        if value:
            return str(value)
    return None


def _patch_panel(runtime: CardRuntime, patch_panel_id: str):
    for patch_panel in runtime.list_patch_panels():
        if patch_panel.id == patch_panel_id:
            return patch_panel
    raise LookupError(f"Patch Panel '{patch_panel_id}' is not registered")
