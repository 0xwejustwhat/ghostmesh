from __future__ import annotations

import sys

from ghostmesh.api.main import create_app
from ghostmesh.mcp import bind_app, run_stdio


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["mcp-server"]:
        app = create_app()
        bind_app(app)
        run_stdio()
        return 0

    command = " ".join(args) if args else "<none>"
    raise SystemExit(f"unknown ghostmesh command: {command}")
