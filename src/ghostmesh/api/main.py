from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ghostmesh.config import Settings, get_settings
from ghostmesh.db import create_database_engine
from ghostmesh.domain import Artifact, Card, CardEvent, Lease, PatchPanel
from ghostmesh.logging import configure_logging
from ghostmesh.runtime import CardRuntime, InMemoryCardRuntime, PostgresCardRuntime
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
    payload: dict[str, Any]


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
    ) -> Artifact:
        return runtime.submit_artifact(
            lease_id=request.lease_id,
            output_pipe=request.output_pipe,
            payload=request.payload,
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

    return app


app = create_app()
