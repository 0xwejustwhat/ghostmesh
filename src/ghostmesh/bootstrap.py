from __future__ import annotations

from dataclasses import dataclass

from ghostmesh.auth import (
    AuthorizationRepository,
    AuthorizationService,
    InMemoryAuthorizationRepository,
    PostgresAuthorizationRepository,
    get_role_template,
    seed_development_authority,
)
from ghostmesh.config import Settings, get_settings
from ghostmesh.db import create_database_engine
from ghostmesh.defaults.bootstrap import BootstrapResult, SystemWorkflowBootstrapper
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PermissionGrant,
    RoleAssignment,
    RoleName,
    Scope,
)
from ghostmesh.registry import (
    InMemoryPatchPanelRegistry,
    PatchPanelRegistry,
    PostgresPatchPanelRegistry,
)
from ghostmesh.runtime import CardRuntime, InMemoryCardRuntime, PostgresCardRuntime


@dataclass(frozen=True)
class SystemInitialization:
    runtime: CardRuntime
    registry: PatchPanelRegistry
    authorization_service: AuthorizationService
    bootstrap_results: list[BootstrapResult]
    root_participant_id: str


def initialize_system(
    settings: Settings | None = None,
    runtime: CardRuntime | None = None,
    registry: PatchPanelRegistry | None = None,
    auth_service: AuthorizationService | None = None,
) -> SystemInitialization:
    """Initialize storage, system graphs, and root authority idempotently."""
    settings = settings or get_settings()
    resolved_runtime = runtime or create_runtime(settings)
    resolved_registry = registry or create_registry(settings)
    resolved_auth_service = auth_service or create_authorization_service(settings)

    bootstrap_results = SystemWorkflowBootstrapper(
        runtime=resolved_runtime,
        registry=resolved_registry,
        patch_panel_paths=settings.system_patch_panel_paths,
    ).bootstrap()
    seed_root_operator(
        resolved_auth_service,
        participant_id=settings.root_participant_id,
    )

    return SystemInitialization(
        runtime=resolved_runtime,
        registry=resolved_registry,
        authorization_service=resolved_auth_service,
        bootstrap_results=bootstrap_results,
        root_participant_id=settings.root_participant_id,
    )


def create_runtime(settings: Settings) -> CardRuntime:
    if settings.runtime_backend == "postgres":
        return PostgresCardRuntime(create_database_engine(settings.database_url))
    return InMemoryCardRuntime()


def create_registry(settings: Settings) -> PatchPanelRegistry:
    if settings.registry_backend == "postgres":
        return PostgresPatchPanelRegistry(create_database_engine(settings.database_url))
    return InMemoryPatchPanelRegistry()


def create_authorization_service(settings: Settings) -> AuthorizationService:
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


def seed_root_operator(
    authorization_service: AuthorizationService,
    *,
    participant_id: str,
) -> None:
    participant = Participant(
        id=participant_id,
        type=ParticipantType.SYSTEM_SERVICE,
        display_name="Root Operator",
        auth_method="local_bootstrap",
        metadata={"system_bootstrap": True, "root_operator": True},
    )
    repository = authorization_service.repository
    repository.upsert_participant(participant)
    ensure_builtin_role_assignment(
        repository,
        participant_id=participant.id,
        role_name=RoleName.ADMIN,
        scope=Scope.global_scope(),
        assigned_by=participant.id,
    )


def ensure_builtin_role_assignment(
    repository: AuthorizationRepository,
    *,
    participant_id: str,
    role_name: RoleName,
    scope: Scope,
    assigned_by: str | None = None,
) -> RoleAssignment:
    template = get_role_template(role_name)
    existing = next(
        (
            assignment
            for assignment in repository.list_role_assignments(participant_id)
            if assignment.role_id == template.id and assignment.scope == scope
        ),
        None,
    )
    if existing is None:
        existing = RoleAssignment(
            participant_id=participant_id,
            role_id=template.id,
            scope=scope,
            assigned_by=assigned_by,
            metadata={"builtin_role": role_name.value},
        )
        repository.add_role_assignment(existing)

    active_grants = repository.list_permission_grants(participant_id)
    for grant in template.permission_grants(scope, granted_by=assigned_by):
        if not _has_matching_grant(active_grants, grant):
            repository.add_permission_grant(grant)
    return existing


def _has_matching_grant(grants: list[PermissionGrant], candidate: PermissionGrant) -> bool:
    return any(
        grant.role_id == candidate.role_id
        and grant.participant_id == candidate.participant_id
        and grant.permission == candidate.permission
        and grant.scope == candidate.scope
        for grant in grants
    )
