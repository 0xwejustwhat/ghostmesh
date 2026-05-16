from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ghostmesh.boundaries import BoundaryAdapterService, BoundarySinkRequest, BoundarySourceRequest
from ghostmesh.config import Settings, get_settings
from ghostmesh.db import create_database_engine
from ghostmesh.domain import (
    ArtifactReference,
    Card,
    CardEvent,
    Lease,
    PatchPanel,
    ProposedMutation,
    ShadowCardLink,
)
from ghostmesh.logging import configure_logging
from ghostmesh.nodes import HumanValidationInput, NodeExecutor, WorkerExecutionInput
from ghostmesh.runtime import (
    CardRuntime,
    InMemoryCardRuntime,
    PostgresCardRuntime,
    ShadowPolicy,
    ShadowService,
)
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError, NotFoundError


class CreateCardRequest(BaseModel):
    patch_panel_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimCardRequest(BaseModel):
    input_pipe: str
    worker_id: str
    lease_seconds: int = 300


class SubmitArtifactRequest(BaseModel):
    lease_id: UUID
    output_pipe: str
    artifact_refs: list[ArtifactReference]


class RenewLeaseRequest(BaseModel):
    lease_seconds: int = 300


class ReleaseLeaseRequest(BaseModel):
    actor_id: str | None = None


class ValidateCardRequest(BaseModel):
    validator_id: str
    accepted: bool
    reason: str | None = None
    output_pipe: str | None = None


class MoveCardRequest(BaseModel):
    to_bucket: str
    actor_id: str | None = None
    reason: str | None = None


class SourceExecutionRequest(BaseModel):
    patch_panel_id: str
    source_id: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkerExecutionRequest(BaseModel):
    patch_panel_id: str
    input_pipe: str
    output_pipe: str
    worker_id: str
    artifact_refs: list[ArtifactReference]
    lease_seconds: int = 300


class HumanValidationExecutionRequest(BaseModel):
    patch_panel_id: str
    card_id: UUID
    validator_id: str
    accepted: bool
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None


class JunctionExecutionRequest(BaseModel):
    patch_panel_id: str
    card_id: UUID
    junction_id: str


class SinkExecutionRequest(BaseModel):
    patch_panel_id: str
    card_id: UUID
    sink_id: str
    external_reference: str | None = None


class CreateShadowRequest(BaseModel):
    production_card_id: UUID
    candidate_id: str
    sample_rate: float = Field(default=1.0, ge=0, le=1)
    max_parallel: int = Field(default=1, ge=1)


class CompleteShadowRequest(BaseModel):
    metrics: dict[str, Any] = Field(default_factory=dict)


class ProposedMutationRequest(BaseModel):
    mutation_type: str
    proposed_by: str
    payload: dict[str, Any]


class MutationValidationRequest(BaseModel):
    accepted: bool
    validator_id: str
    reason: str | None = None


class MutationPromotionRequest(BaseModel):
    patch_panel: PatchPanel


class HumanValidatorDecisionRequest(BaseModel):
    patch_panel_id: str
    accepted: bool
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None


def _create_runtime(settings: Settings) -> CardRuntime:
    if settings.runtime_backend == "postgres":
        return PostgresCardRuntime(create_database_engine(settings.database_url))
    return InMemoryCardRuntime()


def create_app(settings: Settings | None = None, runtime: CardRuntime | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    runtime = runtime or _create_runtime(settings)

    app = FastAPI(
        title="Ghost Mesh",
        version="0.1.0",
        description="Graph-native accountability runtime for human and AI work.",
    )
    app.state.runtime = runtime
    app.state.shadow_service = ShadowService(runtime)

    @app.exception_handler(NotFoundError)
    def handle_not_found(_request: object, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    def handle_conflict(_request: object, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidOperationError)
    def handle_invalid_operation(_request: object, exc: InvalidOperationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/config")
    def health_config() -> dict[str, str]:
        return {
            "environment": settings.environment,
            "database_configured": str(bool(settings.database_url)).lower(),
        }

    @app.get("/patchpanels")
    def list_patch_panels() -> list[PatchPanel]:
        return runtime.list_patch_panels()

    @app.post("/patchpanels")
    def register_patch_panel(patch_panel: PatchPanel) -> PatchPanel:
        return runtime.register_patch_panel(patch_panel)

    @app.get("/cards")
    def list_cards() -> list[Card]:
        return runtime.list_cards()

    @app.post("/cards")
    def create_card(
        request: CreateCardRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Card:
        return runtime.create_card(
            patch_panel_id=request.patch_panel_id,
            payload=request.payload,
            metadata=request.metadata,
            idempotency_key=idempotency_key,
        )

    @app.post("/cards/claim")
    def claim_card(
        request: ClaimCardRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Lease:
        return runtime.claim_card(
            input_pipe=request.input_pipe,
            worker_id=request.worker_id,
            lease_seconds=request.lease_seconds,
            idempotency_key=idempotency_key,
        )

    @app.post("/cards/submit")
    def submit_artifact(
        request: SubmitArtifactRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> list[ArtifactReference]:
        return runtime.submit_artifact(
            lease_id=request.lease_id,
            output_pipe=request.output_pipe,
            artifact_refs=request.artifact_refs,
            idempotency_key=idempotency_key,
        )

    @app.post("/leases/{lease_id}/renew")
    def renew_lease(
        lease_id: UUID,
        request: RenewLeaseRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Lease:
        return runtime.renew_lease(
            lease_id=lease_id,
            lease_seconds=request.lease_seconds,
            idempotency_key=idempotency_key,
        )

    @app.post("/leases/{lease_id}/release")
    def release_lease(
        lease_id: UUID,
        request: ReleaseLeaseRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Lease:
        return runtime.release_lease(
            lease_id=lease_id,
            actor_id=request.actor_id,
            idempotency_key=idempotency_key,
        )

    @app.post("/leases/expire")
    def expire_leases() -> list[Lease]:
        return runtime.expire_leases()

    @app.post("/cards/{card_id}/validate")
    def validate_card(
        card_id: UUID,
        request: ValidateCardRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CardEvent:
        return runtime.validate_card(
            card_id=card_id,
            validator_id=request.validator_id,
            accepted=request.accepted,
            reason=request.reason,
            output_pipe=request.output_pipe,
            idempotency_key=idempotency_key,
        )

    @app.post("/cards/{card_id}/move")
    def move_card(
        card_id: UUID,
        request: MoveCardRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Card:
        return runtime.move_card(
            card_id=card_id,
            to_bucket=request.to_bucket,
            actor_id=request.actor_id,
            reason=request.reason,
            idempotency_key=idempotency_key,
        )

    @app.get("/cards/{card_id}/history")
    def card_history(card_id: UUID) -> list[CardEvent]:
        return runtime.card_history(card_id)

    @app.get("/workers/leases/{lease_id}/context")
    def worker_lease_context(lease_id: UUID) -> dict[str, Any]:
        lease = runtime.get_lease(lease_id)
        card = runtime.get_card(lease.card_id)
        return {
            "lease": lease,
            "card": card,
            "history": runtime.card_history(card.id),
        }

    @app.get("/validators/{validator_id}/cards")
    def list_validator_cards(validator_id: str, patch_panel_id: str) -> list[Card]:
        patch_panel = _patch_panel(runtime, patch_panel_id)
        buckets = _validator_input_buckets(patch_panel, validator_id)
        return [card for card in runtime.list_cards() if card.current_bucket in buckets]

    @app.get("/validators/cards/{card_id}")
    def inspect_validator_card(card_id: UUID) -> dict[str, Any]:
        card = runtime.get_card(card_id)
        return {"card": card, "history": runtime.card_history(card.id)}

    @app.post("/validators/{validator_id}/cards/{card_id}/decision")
    def submit_validator_decision(
        validator_id: str,
        card_id: UUID,
        request: HumanValidatorDecisionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CardEvent:
        executor = _executor(runtime, request.patch_panel_id)
        return executor.execute_human_validator(
            HumanValidationInput(
                card_id=card_id,
                validator_id=validator_id,
                accepted=request.accepted,
                score=request.score,
                reason=request.reason,
                idempotency_key=idempotency_key,
            )
        )

    @app.post("/nodes/source/execute")
    def execute_source(
        request: SourceExecutionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Card:
        executor = _executor(runtime, request.patch_panel_id)
        return executor.execute_source(
            source_id=request.source_id,
            payload=request.payload,
            metadata=request.metadata,
            idempotency_key=idempotency_key,
        )

    @app.post("/nodes/worker/execute")
    def execute_worker(
        request: WorkerExecutionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> list[ArtifactReference]:
        executor = _executor(runtime, request.patch_panel_id)
        return executor.execute_worker(
            WorkerExecutionInput(
                input_pipe=request.input_pipe,
                output_pipe=request.output_pipe,
                worker_id=request.worker_id,
                artifact_refs=request.artifact_refs,
                lease_seconds=request.lease_seconds,
                idempotency_key=idempotency_key,
            )
        )

    @app.post("/nodes/validator/human/execute")
    def execute_human_validator(
        request: HumanValidationExecutionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CardEvent:
        executor = _executor(runtime, request.patch_panel_id)
        return executor.execute_human_validator(
            HumanValidationInput(
                card_id=request.card_id,
                validator_id=request.validator_id,
                accepted=request.accepted,
                score=request.score,
                reason=request.reason,
                idempotency_key=idempotency_key,
            )
        )

    @app.post("/nodes/junction/execute")
    def execute_junction(
        request: JunctionExecutionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        executor = _executor(runtime, request.patch_panel_id)
        decision = executor.execute_junction(
            card_id=request.card_id,
            junction_id=request.junction_id,
            idempotency_key=idempotency_key,
        )
        return {
            "card": decision.card,
            "selected_pipe": decision.selected_pipe,
            "selected_bucket": decision.selected_bucket,
            "accepted": decision.accepted,
        }

    @app.post("/nodes/sink/execute")
    def execute_sink(
        request: SinkExecutionRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        executor = _executor(runtime, request.patch_panel_id)
        result = executor.execute_sink(
            card_id=request.card_id,
            sink_id=request.sink_id,
            external_reference=request.external_reference,
            idempotency_key=idempotency_key,
        )
        return {"event": result.event, "external_reference": result.external_reference}

    @app.post("/boundaries/source")
    def execute_boundary_source(request: BoundarySourceRequest) -> dict[str, Any]:
        result = BoundaryAdapterService(runtime=runtime).execute_source(request)
        return {
            "card": result.card,
            "deduplication_key": result.deduplication_key,
            "adapter": result.adapter,
        }

    @app.post("/boundaries/sink")
    def execute_boundary_sink(request: BoundarySinkRequest) -> dict[str, Any]:
        result = BoundaryAdapterService(runtime=runtime).execute_sink(request)
        return {
            "event": result.event,
            "external_reference": result.external_reference,
            "egress_idempotency_key": result.egress_idempotency_key,
            "adapter": result.adapter,
        }

    @app.post("/shadows")
    def create_shadow(
        request: CreateShadowRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        production_card = runtime.get_card(request.production_card_id)
        run = app.state.shadow_service.create_shadow_card(
            production_card=production_card,
            candidate_id=request.candidate_id,
            policy=ShadowPolicy(
                sample_rate=request.sample_rate,
                max_parallel=request.max_parallel,
            ),
            idempotency_key=idempotency_key,
        )
        return {
            "production_card": run.production_card,
            "shadow_card": run.shadow_card,
            "shadow_metadata": run.shadow_metadata,
        }

    @app.post("/shadows/{link_id}/complete")
    def complete_shadow(link_id: UUID, request: CompleteShadowRequest) -> ShadowCardLink:
        return app.state.shadow_service.complete_shadow(link_id=link_id, metrics=request.metrics)

    @app.post("/mutations")
    def propose_mutation(request: ProposedMutationRequest) -> ProposedMutation:
        return app.state.shadow_service.propose_mutation(
            mutation_type=request.mutation_type,
            proposed_by=request.proposed_by,
            payload=request.payload,
        )

    @app.post("/mutations/{mutation_id}/validate")
    def validate_mutation(
        mutation_id: UUID,
        request: MutationValidationRequest,
    ) -> ProposedMutation:
        return app.state.shadow_service.validate_mutation(
            mutation_id=mutation_id,
            accepted=request.accepted,
            validator_id=request.validator_id,
            reason=request.reason,
        )

    @app.post("/mutations/{mutation_id}/promote")
    def promote_mutation(
        mutation_id: UUID,
        request: MutationPromotionRequest,
    ) -> ProposedMutation:
        return app.state.shadow_service.promote_mutation(
            mutation_id=mutation_id,
            patch_panel=request.patch_panel,
        )

    return app


app = create_app()


def _executor(runtime: CardRuntime, patch_panel_id: str) -> NodeExecutor:
    return NodeExecutor(patch_panel=_patch_panel(runtime, patch_panel_id), runtime=runtime)


def _patch_panel(runtime: CardRuntime, patch_panel_id: str) -> PatchPanel:
    for patch_panel in runtime.list_patch_panels():
        if patch_panel.id == patch_panel_id:
            return patch_panel
    raise NotFoundError(f"Patch Panel '{patch_panel_id}' is not registered")


def _validator_input_buckets(patch_panel: PatchPanel, validator_id: str) -> set[str]:
    for node in patch_panel.nodes:
        if node.id == validator_id:
            return {
                patch_panel.pipe_bindings[pipe].bucket
                for pipe in node.input_pipes
                if pipe in patch_panel.pipe_bindings
            }
    raise NotFoundError(f"validator '{validator_id}' is not registered")
