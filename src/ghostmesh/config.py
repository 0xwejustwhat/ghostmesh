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
    )
