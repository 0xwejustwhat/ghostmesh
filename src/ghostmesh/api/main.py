from __future__ import annotations

from fastapi import FastAPI

from ghostmesh.config import Settings, get_settings
from ghostmesh.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title="Ghost Mesh",
        version="0.1.0",
        description="Graph-native accountability runtime for human and AI work.",
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/health/config")
    def health_config() -> dict[str, str]:
        return {
            "environment": settings.environment,
            "database_configured": str(bool(settings.database_url)).lower(),
        }

    return app


app = create_app()

