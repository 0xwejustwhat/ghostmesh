from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from ghostmesh.auth.service import AuthorizationService
from ghostmesh.domain import PermissionName, Scope

PARTICIPANT_HEADER = "X-Ghostmesh-Participant"


def authorize_request(
    *,
    request: Request,
    permission: PermissionName,
    scope: Scope,
    context: dict[str, Any] | None = None,
    participant_id: str | None = None,
) -> str | None:
    if not getattr(request.app.state, "authorization_enabled", False):
        return participant_id

    resolved_participant_id = request.headers.get(PARTICIPANT_HEADER) or participant_id
    if not resolved_participant_id:
        raise HTTPException(status_code=403, detail="missing Ghost Mesh participant")

    service: AuthorizationService = request.app.state.authorization_service
    decision = service.authorize(
        participant_id=resolved_participant_id,
        permission=permission,
        scope=scope,
        context=context or {},
    )
    if not decision.allowed:
        raise HTTPException(status_code=403, detail=decision.reason)
    return resolved_participant_id
