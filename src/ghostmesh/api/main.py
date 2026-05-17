from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ghostmesh.auth import (
    AuthorizationService,
    InMemoryAuthorizationRepository,
    PostgresAuthorizationRepository,
    get_role_template,
    seed_development_authority,
)
from ghostmesh.auth.dependencies import authorize_request
from ghostmesh.boundaries import BoundaryAdapterService, BoundarySinkRequest, BoundarySourceRequest
from ghostmesh.config import Settings, get_settings
from ghostmesh.db import create_database_engine
from ghostmesh.defaults.bootstrap import SystemWorkflowBootstrapper
from ghostmesh.domain import (
    ArtifactReference,
    AuditAction,
    Card,
    CardEvent,
    GenesisIntent,
    GenesisIntentConstraints,
    Lease,
    Participant,
    ParticipantStatus,
    ParticipantType,
    PatchPanel,
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PermissionGrant,
    PermissionName,
    ProposedMutation,
    RoleAssignment,
    RoleName,
    Scope,
    ScopeType,
    ShadowCardLink,
)
from ghostmesh.genesis import GenesisService
from ghostmesh.logging import configure_logging
from ghostmesh.mcp import mount_mcp_endpoints
from ghostmesh.nodes import NodeExecutor, ValidatorExecutionInput, WorkerExecutionInput
from ghostmesh.observability import ObservabilityService
from ghostmesh.registry import (
    InMemoryPatchPanelRegistry,
    PatchPanelRegistry,
    PatchPanelRegistrySearch,
    PostgresPatchPanelRegistry,
)
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


class ValidatorExecutionRequest(BaseModel):
    patch_panel_id: str
    card_id: UUID
    validator_id: str
    accepted: bool | None = None
    selected_exit: str | None = None
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


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
    selected_exit: str | None = None
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None


class RegisterPatchPanelRegistryRequest(BaseModel):
    patch_panel: PatchPanel
    registry_metadata: PatchPanelRegistryMetadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupersedeRegistryEntryRequest(BaseModel):
    superseded_by_entry_id: UUID


class CreateParticipantRequest(BaseModel):
    id: str
    type: ParticipantType
    display_name: str | None = None
    status: ParticipantStatus = ParticipantStatus.ACTIVE
    trust_level: str | None = None
    auth_method: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AssignRoleRequest(BaseModel):
    role_name: RoleName
    scope: Scope
    assigned_by: str | None = None


class GrantPermissionRequest(BaseModel):
    permission: PermissionName
    scope: Scope
    granted_by: str | None = None


class GenesisIntentRequest(BaseModel):
    requested_by: str
    deduplication_key: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    input_type: str
    desired_outputs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    constraints: GenesisIntentConstraints = Field(default_factory=GenesisIntentConstraints)
    launch_if_existing: bool = True
    propose_if_missing: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class LaunchGenesisIntentRequest(BaseModel):
    registry_entry_id: UUID | None = None


class ProposeGenesisIntentRequest(BaseModel):
    proposed_by: str
    candidate_definition: PatchPanel
    registry_metadata: PatchPanelRegistryMetadata
    base_patch_panel_id: str | None = None
    base_version: str | None = None


def _create_runtime(settings: Settings) -> CardRuntime:
    if settings.runtime_backend == "postgres":
        return PostgresCardRuntime(create_database_engine(settings.database_url))
    return InMemoryCardRuntime()


def _create_registry(settings: Settings) -> PatchPanelRegistry:
    if settings.registry_backend == "postgres":
        return PostgresPatchPanelRegistry(create_database_engine(settings.database_url))
    return InMemoryPatchPanelRegistry()


def _create_authorization_service(settings: Settings) -> AuthorizationService:
    if settings.authorization_repository == "postgres":
        return AuthorizationService(
            PostgresAuthorizationRepository(create_database_engine(settings.database_url))
        )

    repository = InMemoryAuthorizationRepository()
    if settings.development_authority_enabled:
        repository = seed_development_authority(
            participant_id=settings.development_participant_id,
            scope=Scope.development_global(),
        )
    return AuthorizationService(repository)


def create_app(
    settings: Settings | None = None,
    runtime: CardRuntime | None = None,
    authorization_service: AuthorizationService | None = None,
    registry: PatchPanelRegistry | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)
    runtime = runtime or _create_runtime(settings)
    authorization_service = authorization_service or _create_authorization_service(settings)
    registry = registry or _create_registry(settings)
    bootstrap_results = SystemWorkflowBootstrapper(
        runtime=runtime,
        registry=registry,
        patch_panel_paths=settings.system_patch_panel_paths,
    ).bootstrap()

    app = FastAPI(
        title="Ghost Mesh",
        version="0.1.0",
        description="Graph-native accountability runtime for human and AI work.",
    )
    app.state.runtime = runtime
    app.state.shadow_service = ShadowService(runtime)
    app.state.registry = registry
    app.state.system_bootstrap_results = bootstrap_results
    app.state.genesis_service = GenesisService(runtime=runtime, registry=registry)
    app.state.authorization_enabled = settings.authorization_enabled
    app.state.authorization_service = authorization_service
    mount_mcp_endpoints(app)

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

    @app.get("/participants")
    def list_participants(http_request: Request) -> list[Participant]:
        _authorize(
            http_request,
            PermissionName.PARTICIPANT_MANAGE,
            Scope(type=ScopeType.GLOBAL),
            context={"operation": "participants.list"},
        )
        return authorization_service.repository.list_participants()

    @app.post("/participants")
    def create_participant(
        request: CreateParticipantRequest,
        http_request: Request,
    ) -> Participant:
        _authorize(
            http_request,
            PermissionName.PARTICIPANT_MANAGE,
            Scope(type=ScopeType.GLOBAL),
            context={"operation": "participants.create", "participant_id": request.id},
        )
        participant = Participant(
            id=request.id,
            type=request.type,
            display_name=request.display_name,
            status=request.status,
            trust_level=request.trust_level,
            auth_method=request.auth_method,
            metadata=request.metadata,
        )
        authorization_service.repository.upsert_participant(participant)
        return participant

    @app.post("/participants/{participant_id}/roles")
    def assign_participant_role(
        participant_id: str,
        request: AssignRoleRequest,
        http_request: Request,
    ) -> RoleAssignment:
        _authorize(
            http_request,
            PermissionName.PERMISSION_GRANT,
            request.scope,
            participant_id=request.assigned_by,
            context={
                "operation": "participants.assign_role",
                "participant_id": participant_id,
                "role_name": request.role_name.value,
            },
        )
        template = get_role_template(request.role_name)
        assignment = RoleAssignment(
            participant_id=participant_id,
            role_id=template.id,
            scope=request.scope,
            assigned_by=_resolved_actor(http_request, request.assigned_by),
            metadata={"builtin_role": request.role_name.value},
        )
        authorization_service.repository.add_role_assignment(assignment)
        for grant in template.permission_grants(
            request.scope,
            granted_by=_resolved_actor(http_request, request.assigned_by),
        ):
            authorization_service.repository.add_permission_grant(grant)
        return assignment

    @app.post("/participants/{participant_id}/permissions")
    def grant_participant_permission(
        participant_id: str,
        request: GrantPermissionRequest,
        http_request: Request,
    ) -> PermissionGrant:
        _authorize(
            http_request,
            PermissionName.PERMISSION_GRANT,
            request.scope,
            participant_id=request.granted_by,
            context={
                "operation": "participants.grant_permission",
                "participant_id": participant_id,
                "permission": request.permission.value,
            },
        )
        grant = PermissionGrant(
            participant_id=participant_id,
            permission=request.permission,
            scope=request.scope,
            granted_by=_resolved_actor(http_request, request.granted_by),
        )
        authorization_service.repository.add_permission_grant(grant)
        return grant

    @app.get("/participants/{participant_id}/permissions")
    def inspect_participant_permissions(
        participant_id: str,
        http_request: Request,
    ) -> list[PermissionGrant]:
        _authorize(
            http_request,
            PermissionName.PERMISSION_GRANT,
            Scope(type=ScopeType.GLOBAL),
            context={
                "operation": "participants.inspect_permissions",
                "participant_id": participant_id,
            },
        )
        return authorization_service.repository.list_permission_grants(participant_id)

    @app.get("/ops/topology/{patch_panel_id}")
    def operator_topology(patch_panel_id: str, http_request: Request) -> dict[str, Any]:
        _authorize_ops_read(http_request, patch_panel_id=patch_panel_id)
        return ObservabilityService(runtime=runtime).topology(patch_panel_id)

    @app.get("/ops/cards/by-bucket")
    def operator_cards_by_bucket(http_request: Request) -> dict[str, list[Card]]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).cards_by_bucket()

    @app.get("/ops/buckets/load")
    def operator_bucket_load(http_request: Request) -> dict[str, int]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).bucket_load()

    @app.get("/ops/leases/active")
    def operator_active_leases(http_request: Request) -> list[dict[str, Any]]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).active_leases()

    @app.get("/ops/workers/activity")
    def operator_worker_activity(http_request: Request) -> dict[str, dict[str, int]]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).worker_activity()

    @app.get("/ops/validators/decisions")
    def operator_validator_decisions(http_request: Request) -> list[dict[str, Any]]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).validator_decisions()

    @app.get("/ops/workflow-versions")
    def operator_workflow_versions(http_request: Request) -> list[dict[str, Any]]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).workflow_versions()

    @app.get("/ops/failed-movements")
    def operator_failed_movements(http_request: Request) -> list[CardEvent]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).failed_movements()

    @app.get("/ops/metrics")
    def operator_metrics(http_request: Request) -> dict[str, Any]:
        _authorize_ops_read(http_request)
        return ObservabilityService(runtime=runtime).metrics()

    @app.get("/ops/dashboard/{patch_panel_id}")
    def operator_dashboard(patch_panel_id: str, http_request: Request) -> dict[str, Any]:
        _authorize_ops_read(http_request, patch_panel_id=patch_panel_id)
        return ObservabilityService(runtime=runtime).dashboard(patch_panel_id)

    @app.get("/patchpanels")
    def list_patch_panels() -> list[PatchPanel]:
        return runtime.list_patch_panels()

    @app.post("/patchpanels")
    def register_patch_panel(patch_panel: PatchPanel, http_request: Request) -> PatchPanel:
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_CREATE,
            Scope(type=ScopeType.PATCH_PANEL, id=patch_panel.id),
            context={"patch_panel_id": patch_panel.id},
        )
        return runtime.register_patch_panel(patch_panel)

    @app.get("/registry/patchpanels")
    def search_patch_panel_registry(
        http_request: Request,
        tag: str | None = None,
        input_type: str | None = None,
        output_type: str | None = None,
        required_tool: str | None = None,
        risk_level: str | None = None,
        owner_participant_id: str | None = None,
        include_archived: bool = False,
        include_superseded: bool = False,
    ) -> list[PatchPanelRegistryEntry]:
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_DISCOVER,
            Scope(type=ScopeType.GLOBAL),
            context={
                "tag": tag,
                "input_type": input_type,
                "output_type": output_type,
                "required_tool": required_tool,
                "risk_level": risk_level,
                "owner_participant_id": owner_participant_id,
            },
        )
        return registry.search(
            PatchPanelRegistrySearch(
                tag=tag,
                input_type=input_type,
                output_type=output_type,
                required_tool=required_tool,
                risk_level=risk_level,
                owner_participant_id=owner_participant_id,
                include_archived=include_archived,
                include_superseded=include_superseded,
            )
        )

    @app.post("/registry/patchpanels")
    def register_patch_panel_registry_entry(
        request: RegisterPatchPanelRegistryRequest,
        http_request: Request,
    ) -> PatchPanelRegistryEntry:
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_CREATE,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel.id),
            context={"patch_panel_id": request.patch_panel.id},
        )
        patch_panel = runtime.register_patch_panel(request.patch_panel)
        entry = PatchPanelRegistryEntry.from_patch_panel(
            patch_panel,
            request.registry_metadata,
            metadata=request.metadata,
        )
        return registry.register(entry)

    @app.get("/registry/patchpanels/{entry_id}")
    def get_patch_panel_registry_entry(
        entry_id: UUID,
        http_request: Request,
    ) -> PatchPanelRegistryEntry:
        entry = registry.get(entry_id)
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_DISCOVER,
            Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            context={"patch_panel_id": entry.patch_panel_id},
        )
        return entry

    @app.patch("/registry/patchpanels/{entry_id}")
    def update_patch_panel_registry_entry(
        entry_id: UUID,
        request: PatchPanelRegistryMetadata,
        http_request: Request,
    ) -> PatchPanelRegistryEntry:
        entry = registry.get(entry_id)
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_EDIT_DRAFT,
            Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            context={"patch_panel_id": entry.patch_panel_id},
        )
        return registry.update_metadata(entry_id, request)

    @app.post("/registry/patchpanels/{entry_id}/archive")
    def archive_patch_panel_registry_entry(
        entry_id: UUID,
        http_request: Request,
    ) -> PatchPanelRegistryEntry:
        entry = registry.get(entry_id)
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_ARCHIVE,
            Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            context={"patch_panel_id": entry.patch_panel_id},
        )
        return registry.archive(entry_id)

    @app.post("/registry/patchpanels/{entry_id}/supersede")
    def supersede_patch_panel_registry_entry(
        entry_id: UUID,
        request: SupersedeRegistryEntryRequest,
        http_request: Request,
    ) -> PatchPanelRegistryEntry:
        entry = registry.get(entry_id)
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_ARCHIVE,
            Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            context={
                "patch_panel_id": entry.patch_panel_id,
                "superseded_by_entry_id": str(request.superseded_by_entry_id),
            },
        )
        return registry.supersede(entry_id, request.superseded_by_entry_id)

    @app.post("/genesis/intents")
    def receive_genesis_intent(
        request: GenesisIntentRequest,
        http_request: Request,
    ) -> GenesisIntent:
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_DISCOVER,
            Scope(type=ScopeType.GLOBAL),
            participant_id=request.requested_by,
            context={
                "deduplication_key": request.deduplication_key,
                "input_type": request.input_type,
                "tags": request.tags,
            },
        )
        intent = app.state.genesis_service.receive_intent(
            requested_by=request.requested_by,
            deduplication_key=request.deduplication_key,
            goal=request.goal,
            input_type=request.input_type,
            desired_outputs=request.desired_outputs,
            tags=request.tags,
            constraints=request.constraints,
            launch_if_existing=request.launch_if_existing,
            propose_if_missing=request.propose_if_missing,
            metadata=request.metadata,
        )
        _record_audit(
            http_request,
            action=AuditAction.GENESIS_INTENT_RECEIVED,
            participant_id=_resolved_actor(http_request, request.requested_by),
            permission=PermissionName.PATCH_PANEL_DISCOVER,
            scope=Scope(type=ScopeType.GLOBAL),
            target_ref=str(intent.id),
            metadata={"candidate_count": len(intent.candidate_registry_entry_ids)},
        )
        _record_audit(
            http_request,
            action=AuditAction.GENESIS_REGISTRY_SEARCHED,
            participant_id=_resolved_actor(http_request, request.requested_by),
            permission=PermissionName.PATCH_PANEL_DISCOVER,
            scope=Scope(type=ScopeType.GLOBAL),
            target_ref=str(intent.id),
            metadata={
                "candidate_registry_entry_ids": [
                    str(entry_id) for entry_id in intent.candidate_registry_entry_ids
                ],
            },
        )
        if not intent.candidate_registry_entry_ids and request.propose_if_missing:
            _record_audit(
                http_request,
                action=AuditAction.GENESIS_DESIGN_REQUIRED,
                participant_id=_resolved_actor(http_request, request.requested_by),
                permission=PermissionName.MUTATION_PROPOSE,
                scope=Scope(type=ScopeType.GLOBAL),
                target_ref=str(intent.id),
                metadata={"input_type": intent.input_type, "tags": intent.tags},
            )
        return intent

    @app.get("/genesis/intents/{intent_id}")
    def get_genesis_intent(intent_id: UUID, http_request: Request) -> GenesisIntent:
        intent = app.state.genesis_service.get(intent_id)
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_DISCOVER,
            Scope(type=ScopeType.GLOBAL),
            participant_id=intent.requested_by,
            context={"genesis_intent_id": str(intent_id)},
        )
        return intent

    @app.post("/genesis/intents/{intent_id}/launch")
    def launch_genesis_intent(
        intent_id: UUID,
        request: LaunchGenesisIntentRequest,
        http_request: Request,
    ) -> Card:
        intent = app.state.genesis_service.get(intent_id)
        selected_id = request.registry_entry_id or (
            intent.candidate_registry_entry_ids[0]
            if intent.candidate_registry_entry_ids
            else None
        )
        if selected_id is None:
            raise ConflictError("genesis intent has no registry candidate to launch")
        entry = registry.get(selected_id)
        _authorize(
            http_request,
            PermissionName.CARD_CREATE,
            Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            participant_id=intent.requested_by,
            context={
                "genesis_intent_id": str(intent_id),
                "patch_panel_id": entry.patch_panel_id,
            },
        )
        card = app.state.genesis_service.launch(intent_id=intent_id, registry_entry_id=selected_id)
        _record_audit(
            http_request,
            action=AuditAction.GENESIS_CANDIDATE_SELECTED,
            participant_id=_resolved_actor(http_request, intent.requested_by),
            permission=PermissionName.PATCH_PANEL_DISCOVER,
            scope=Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            target_ref=str(entry.id),
            metadata={"genesis_intent_id": str(intent_id)},
        )
        _record_audit(
            http_request,
            action=AuditAction.GENESIS_CARD_CREATED,
            participant_id=_resolved_actor(http_request, intent.requested_by),
            permission=PermissionName.CARD_CREATE,
            scope=Scope(type=ScopeType.PATCH_PANEL, id=entry.patch_panel_id),
            target_ref=str(card.id),
            metadata={"genesis_intent_id": str(intent_id)},
        )
        return card

    @app.post("/genesis/intents/{intent_id}/propose")
    def propose_genesis_intent(
        intent_id: UUID,
        request: ProposeGenesisIntentRequest,
        http_request: Request,
    ) -> Card:
        _authorize(
            http_request,
            PermissionName.MUTATION_PROPOSE,
            Scope(type=ScopeType.PATCH_PANEL, id=request.candidate_definition.id),
            participant_id=request.proposed_by,
            context={"genesis_intent_id": str(intent_id)},
        )
        card = app.state.genesis_service.propose(
            intent_id=intent_id,
            proposed_by=request.proposed_by,
            candidate_definition=request.candidate_definition,
            registry_metadata=request.registry_metadata,
            base_patch_panel_id=request.base_patch_panel_id,
            base_version=request.base_version,
        )
        _record_audit(
            http_request,
            action=AuditAction.GENESIS_PROPOSAL_SUBMITTED,
            participant_id=_resolved_actor(http_request, request.proposed_by),
            permission=PermissionName.MUTATION_PROPOSE,
            scope=Scope(type=ScopeType.PATCH_PANEL, id=request.candidate_definition.id),
            target_ref=str(card.id),
            metadata={"genesis_intent_id": str(intent_id)},
        )
        return card

    @app.get("/cards")
    def list_cards() -> list[Card]:
        return runtime.list_cards()

    @app.post("/cards")
    def create_card(
        request: CreateCardRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Card:
        _authorize(
            http_request,
            PermissionName.CARD_CREATE,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel_id),
            context={"patch_panel_id": request.patch_panel_id},
        )
        return runtime.create_card(
            patch_panel_id=request.patch_panel_id,
            payload=request.payload,
            metadata=request.metadata,
            idempotency_key=idempotency_key,
        )

    @app.post("/cards/claim")
    def claim_card(
        request: ClaimCardRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Lease:
        _authorize(
            http_request,
            PermissionName.CARD_CLAIM,
            Scope(type=ScopeType.BUCKET, id=request.input_pipe),
            context={"input_pipe": request.input_pipe, "worker_id": request.worker_id},
        )
        return runtime.claim_card(
            input_pipe=request.input_pipe,
            worker_id=request.worker_id,
            lease_seconds=request.lease_seconds,
            idempotency_key=idempotency_key,
        )

    @app.post("/cards/submit")
    def submit_artifact(
        request: SubmitArtifactRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> list[ArtifactReference]:
        lease = runtime.get_lease(request.lease_id)
        _authorize(
            http_request,
            PermissionName.CARD_SUBMIT_ARTIFACT,
            Scope(type=ScopeType.CARD, id=str(lease.card_id)),
            context={"lease_id": str(request.lease_id), "output_pipe": request.output_pipe},
        )
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
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Lease:
        lease = runtime.get_lease(lease_id)
        _authorize(
            http_request,
            PermissionName.CARD_RELEASE,
            Scope(type=ScopeType.CARD, id=str(lease.card_id)),
            participant_id=request.actor_id,
            context={"lease_id": str(lease_id)},
        )
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
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CardEvent:
        _authorize(
            http_request,
            PermissionName.VALIDATION_SUBMIT,
            Scope(type=ScopeType.CARD, id=str(card_id)),
            participant_id=request.validator_id,
            context={"validator_id": request.validator_id},
        )
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
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CardEvent:
        _authorize(
            http_request,
            PermissionName.VALIDATION_SUBMIT,
            Scope(type=ScopeType.CARD, id=str(card_id)),
            participant_id=validator_id,
            context={"patch_panel_id": request.patch_panel_id, "validator_id": validator_id},
        )
        executor = _executor(runtime, registry, request.patch_panel_id)
        return executor.execute_validator(
            ValidatorExecutionInput(
                card_id=card_id,
                validator_id=validator_id,
                accepted=request.accepted,
                selected_exit=request.selected_exit,
                score=request.score,
                reason=request.reason,
                idempotency_key=idempotency_key,
            )
        )

    @app.post("/nodes/source/execute")
    def execute_source(
        request: SourceExecutionRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> Card:
        _authorize(
            http_request,
            PermissionName.BOUNDARY_SOURCE_INGRESS,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel_id),
            context={"patch_panel_id": request.patch_panel_id, "source_id": request.source_id},
        )
        executor = _executor(runtime, registry, request.patch_panel_id)
        return executor.execute_source(
            source_id=request.source_id,
            payload=request.payload,
            metadata=request.metadata,
            idempotency_key=idempotency_key,
        )

    @app.post("/nodes/worker/execute")
    def execute_worker(
        request: WorkerExecutionRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> list[ArtifactReference]:
        _authorize(
            http_request,
            PermissionName.CARD_SUBMIT_ARTIFACT,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel_id),
            participant_id=request.worker_id,
            context={"patch_panel_id": request.patch_panel_id, "worker_id": request.worker_id},
        )
        executor = _executor(runtime, registry, request.patch_panel_id)
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

    @app.post("/nodes/validator/execute")
    def execute_validator(
        request: ValidatorExecutionRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> CardEvent:
        _authorize(
            http_request,
            PermissionName.VALIDATION_SUBMIT,
            Scope(type=ScopeType.CARD, id=str(request.card_id)),
            participant_id=request.validator_id,
            context={
                "patch_panel_id": request.patch_panel_id,
                "validator_id": request.validator_id,
            },
        )
        executor = _executor(runtime, registry, request.patch_panel_id)
        return executor.execute_validator(
            ValidatorExecutionInput(
                card_id=request.card_id,
                validator_id=request.validator_id,
                accepted=request.accepted,
                selected_exit=request.selected_exit,
                score=request.score,
                reason=request.reason,
                payload=request.payload,
                idempotency_key=idempotency_key,
            )
        )

    @app.post("/nodes/sink/execute")
    def execute_sink(
        request: SinkExecutionRequest,
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        _authorize(
            http_request,
            PermissionName.SINK_EXECUTE,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel_id),
            context={"patch_panel_id": request.patch_panel_id, "sink_id": request.sink_id},
        )
        executor = _executor(runtime, registry, request.patch_panel_id)
        result = executor.execute_sink(
            card_id=request.card_id,
            sink_id=request.sink_id,
            external_reference=request.external_reference,
            idempotency_key=idempotency_key,
        )
        return {"event": result.event, "external_reference": result.external_reference}

    @app.post("/boundaries/source")
    def execute_boundary_source(
        request: BoundarySourceRequest,
        http_request: Request,
    ) -> dict[str, Any]:
        _authorize(
            http_request,
            PermissionName.BOUNDARY_SOURCE_INGRESS,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel_id),
            context={"patch_panel_id": request.patch_panel_id},
        )
        result = BoundaryAdapterService(runtime=runtime).execute_source(request)
        return {
            "card": result.card,
            "deduplication_key": result.deduplication_key,
            "adapter": result.adapter,
        }

    @app.post("/boundaries/sink")
    def execute_boundary_sink(
        request: BoundarySinkRequest,
        http_request: Request,
    ) -> dict[str, Any]:
        _authorize(
            http_request,
            PermissionName.BOUNDARY_SINK_EGRESS,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel_id),
            context={"patch_panel_id": request.patch_panel_id},
        )
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
        http_request: Request,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> dict[str, Any]:
        _authorize(
            http_request,
            PermissionName.SHADOW_CREATE,
            Scope(type=ScopeType.CARD, id=str(request.production_card_id)),
            context={"candidate_id": request.candidate_id},
        )
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
    def complete_shadow(
        link_id: UUID, request: CompleteShadowRequest, http_request: Request
    ) -> ShadowCardLink:
        _authorize(
            http_request,
            PermissionName.SHADOW_COMPLETE,
            Scope(type=ScopeType.GLOBAL),
            context={"shadow_link_id": str(link_id)},
        )
        return app.state.shadow_service.complete_shadow(link_id=link_id, metrics=request.metrics)

    @app.post("/mutations")
    def propose_mutation(
        request: ProposedMutationRequest,
        http_request: Request,
    ) -> ProposedMutation:
        _authorize(
            http_request,
            PermissionName.MUTATION_PROPOSE,
            Scope(type=ScopeType.GLOBAL),
            participant_id=request.proposed_by,
            context={"mutation_type": request.mutation_type},
        )
        return app.state.shadow_service.propose_mutation(
            mutation_type=request.mutation_type,
            proposed_by=request.proposed_by,
            payload=request.payload,
        )

    @app.post("/mutations/{mutation_id}/validate")
    def validate_mutation(
        mutation_id: UUID,
        request: MutationValidationRequest,
        http_request: Request,
    ) -> ProposedMutation:
        _authorize(
            http_request,
            PermissionName.MUTATION_VALIDATE,
            Scope(type=ScopeType.GLOBAL),
            participant_id=request.validator_id,
            context={"mutation_id": str(mutation_id)},
        )
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
        http_request: Request,
    ) -> ProposedMutation:
        _authorize(
            http_request,
            PermissionName.MUTATION_PROMOTE,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel.id),
            context={"mutation_id": str(mutation_id), "patch_panel_id": request.patch_panel.id},
        )
        _authorize(
            http_request,
            PermissionName.PATCH_PANEL_PUBLISH_VERSION,
            Scope(type=ScopeType.PATCH_PANEL, id=request.patch_panel.id),
            context={"mutation_id": str(mutation_id), "patch_panel_id": request.patch_panel.id},
        )
        return app.state.shadow_service.promote_mutation(
            mutation_id=mutation_id,
            patch_panel=request.patch_panel,
        )

    return app


app = create_app()


def _executor(
    runtime: CardRuntime,
    registry: PatchPanelRegistry,
    patch_panel_id: str,
) -> NodeExecutor:
    return NodeExecutor(
        patch_panel=_patch_panel(runtime, patch_panel_id),
        runtime=runtime,
        registry=registry,
    )


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


def _authorize(
    request: Request,
    permission: PermissionName,
    scope: Scope,
    *,
    participant_id: str | None = None,
    context: dict[str, Any] | None = None,
) -> str | None:
    return authorize_request(
        request=request,
        permission=permission,
        scope=scope,
        participant_id=participant_id,
        context=context,
    )


def _authorize_ops_read(request: Request, *, patch_panel_id: str | None = None) -> str | None:
    scope = (
        Scope(type=ScopeType.PATCH_PANEL, id=patch_panel_id)
        if patch_panel_id
        else Scope(type=ScopeType.GLOBAL)
    )
    return _authorize(
        request,
        PermissionName.AUDIT_VIEW,
        scope,
        context={"patch_panel_id": patch_panel_id} if patch_panel_id else {},
    )


def _resolved_actor(request: Request, fallback: str | None) -> str:
    return request.headers.get("X-Ghostmesh-Participant") or fallback or "unknown"


def _record_audit(
    request: Request,
    *,
    action: AuditAction,
    participant_id: str | None,
    permission: PermissionName | None,
    scope: Scope,
    target_ref: str,
    reason: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    service: AuthorizationService = request.app.state.authorization_service
    service.record_event(
        action=action,
        participant_id=participant_id,
        permission=permission,
        scope=scope,
        allowed=True,
        reason=reason,
        target_ref=target_ref,
        metadata=metadata,
    )
