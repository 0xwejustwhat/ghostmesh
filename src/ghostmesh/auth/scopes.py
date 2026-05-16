from __future__ import annotations

from typing import Any

from ghostmesh.domain import Scope, ScopeType


def scope_matches(
    grant_scope: Scope,
    target_scope: Scope,
    context: dict[str, Any] | None = None,
) -> bool:
    context = context or {}
    if grant_scope.type in {ScopeType.GLOBAL, ScopeType.DEVELOPMENT_GLOBAL}:
        return True
    if grant_scope.type == target_scope.type and grant_scope.id == target_scope.id:
        return True
    if grant_scope.type == ScopeType.WORKFLOW:
        return grant_scope.id is not None and grant_scope.id == context.get("workflow_id")
    if grant_scope.type == ScopeType.PATCH_PANEL:
        if target_scope.type == ScopeType.VERSION:
            return grant_scope.id is not None and grant_scope.id == context.get("patch_panel_id")
        return grant_scope.id is not None and grant_scope.id == context.get("patch_panel_id")
    return False
