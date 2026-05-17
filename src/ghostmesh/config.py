from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "postgresql+psycopg://ghostmesh:ghostmesh@localhost:5432/ghostmesh"
    log_level: str = "INFO"
    runtime_backend: str = "memory"
    registry_backend: str = "memory"
    authorization_enabled: bool = False
    authorization_repository: str = "memory"
    development_authority_enabled: bool = False
    development_participant_id: str = "dev-admin"
    system_patch_panel_paths: tuple[str, ...] = (
        "src/ghostmesh/defaults/patchpanels/system-pp-approval.yaml",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings(
        environment=os.getenv("GHOSTMESH_ENVIRONMENT", "development"),
        database_url=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://ghostmesh:ghostmesh@localhost:5432/ghostmesh",
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        runtime_backend=os.getenv("GHOSTMESH_RUNTIME_BACKEND", "memory"),
        registry_backend=os.getenv("GHOSTMESH_REGISTRY_BACKEND", "memory"),
        authorization_enabled=_env_bool("GHOSTMESH_AUTHORIZATION_ENABLED", False),
        authorization_repository=os.getenv("GHOSTMESH_AUTHORIZATION_REPOSITORY", "memory"),
        development_authority_enabled=_env_bool("GHOSTMESH_DEVELOPMENT_AUTHORITY_ENABLED", False),
        development_participant_id=os.getenv("GHOSTMESH_DEVELOPMENT_PARTICIPANT_ID", "dev-admin"),
        system_patch_panel_paths=_env_list(
            "GHOSTMESH_SYSTEM_PATCH_PANEL_PATHS",
            ("src/ghostmesh/defaults/patchpanels/system-pp-approval.yaml",),
        ),
    )


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def _env_list(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = os.getenv(name)
    if value is None:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default
