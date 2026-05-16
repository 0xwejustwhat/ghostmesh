"""Authorization primitives and services for Ghost Mesh."""

from ghostmesh.auth.catalog import (
    BUILT_IN_ROLE_TEMPLATES,
    RoleTemplate,
    assign_role_to_participant,
    built_in_roles,
    get_role_template,
    seed_development_authority,
)
from ghostmesh.auth.repositories import (
    AuthorizationRepository,
    InMemoryAuthorizationRepository,
    PostgresAuthorizationRepository,
)
from ghostmesh.auth.scopes import scope_matches
from ghostmesh.auth.service import AuthorizationService

__all__ = [
    "AuthorizationRepository",
    "AuthorizationService",
    "BUILT_IN_ROLE_TEMPLATES",
    "InMemoryAuthorizationRepository",
    "PostgresAuthorizationRepository",
    "RoleTemplate",
    "assign_role_to_participant",
    "built_in_roles",
    "get_role_template",
    "seed_development_authority",
    "scope_matches",
]
