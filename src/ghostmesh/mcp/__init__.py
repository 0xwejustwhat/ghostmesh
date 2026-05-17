"""MCP protocol interface for Ghost Mesh."""

from ghostmesh.mcp.server import bind_app, mcp, mount_mcp_endpoints, run_stdio

__all__ = ["bind_app", "mcp", "mount_mcp_endpoints", "run_stdio"]
