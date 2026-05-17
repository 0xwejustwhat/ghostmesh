from __future__ import annotations

import sys

from fastapi import FastAPI

from ghostmesh.bootstrap import initialize_system
from ghostmesh.config import get_settings
from ghostmesh.logging import configure_logging
from ghostmesh.mcp import bind_app, run_stdio


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["mcp-server"]:
        settings = get_settings()
        configure_logging(settings.log_level)
        initialized = initialize_system(settings=settings)
        app = FastAPI()
        app.state.runtime = initialized.runtime
        app.state.registry = initialized.registry
        app.state.authorization_enabled = settings.authorization_enabled
        app.state.authorization_service = initialized.authorization_service
        app.state.system_bootstrap_results = initialized.bootstrap_results
        app.state.root_participant_id = initialized.root_participant_id
        bind_app(app)
        run_stdio()
        return 0

    command = " ".join(args) if args else "<none>"
    raise SystemExit(f"unknown ghostmesh command: {command}")
