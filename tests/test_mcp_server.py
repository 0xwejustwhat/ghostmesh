from __future__ import annotations

import json
from pathlib import Path

import pytest
from starlette.routing import Mount

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import Participant, ParticipantType
from ghostmesh.mcp import mcp
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import InMemoryPatchPanelRegistry
from ghostmesh.runtime import InMemoryCardRuntime
from tests.helpers import artifact_ref

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _json_result(content: object) -> dict[str, object]:
    if hasattr(content, "structured_content"):
        return content.structured_content  # type: ignore[no-any-return]
    first = content[0]  # type: ignore[index]
    return json.loads(first.text)  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_mcp_tool_schema_lists_canonical_tools() -> None:
    tools = await mcp.list_tools()
    names = {tool.name for tool in tools}

    assert {
        "ghostmesh.claim_card",
        "ghostmesh.submit_artifact",
        "ghostmesh.submit_validator_decision",
        "ghostmesh.boundary_source",
        "ghostmesh.boundary_sink",
    }.issubset(names)
    claim_tool = next(tool for tool in tools if tool.name == "ghostmesh.claim_card")
    assert "worker_id" in claim_tool.parameters["properties"]
    assert "input_pipe" in claim_tool.parameters["properties"]


def test_mcp_endpoints_are_mounted_on_fastapi_app() -> None:
    app = create_app(settings=Settings())
    mcp_mount = next(
        route for route in app.routes if isinstance(route, Mount) and route.path == "/mcp"
    )

    mounted_paths = {route.path for route in mcp_mount.app.routes}

    assert "/sse" in mounted_paths
    assert "/messages" in mounted_paths


def test_mcp_server_uses_fastmcp_3_native_transport() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "src" / "ghostmesh" / "mcp" / "server.py"
    ).read_text()

    assert "SseServerTransport" not in source
    assert "_mcp_server" not in source
    assert "_sse_app" not in source


@pytest.mark.anyio
async def test_mcp_claim_and_submit_artifact_use_runtime_directly() -> None:
    runtime = InMemoryCardRuntime()
    create_app(settings=Settings(), runtime=runtime, registry=InMemoryPatchPanelRegistry())
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    card = runtime.create_card(patch_panel_id="hello_world", payload={"title": "MCP"})

    claim_content = await mcp.call_tool(
        "ghostmesh.claim_card",
        {"worker_id": "worker-1", "input_pipe": "worker_input"},
    )
    lease = _json_result(claim_content)
    submit_content = await mcp.call_tool(
        "ghostmesh.submit_artifact",
        {
            "lease_id": lease["id"],
            "output_pipe": "worker_output",
            "artifact_refs": [artifact_ref(card.id).model_dump(mode="json")],
        },
    )

    submitted = _json_result(submit_content)
    assert lease["card_id"] == str(card.id)
    assert submitted["artifact_refs"][0]["card_id"] == str(card.id)
    assert runtime.get_card(card.id).current_bucket == "validation_inbox"


@pytest.mark.anyio
async def test_mcp_validator_decision_records_card_event_and_routes() -> None:
    runtime = InMemoryCardRuntime()
    create_app(settings=Settings(), runtime=runtime, registry=InMemoryPatchPanelRegistry())
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)
    card = runtime.create_card(patch_panel_id="hello_world", payload={"title": "Validate"})
    runtime.move_card(card_id=card.id, to_bucket="validation_inbox")

    content = await mcp.call_tool(
        "ghostmesh.submit_validator_decision",
        {
            "validator_id": "human_validator",
            "card_id": str(card.id),
            "patch_panel_id": "hello_world",
            "accepted": True,
            "selected_exit": "publish",
            "score": 9,
            "reason": "MCP accepted",
        },
    )
    event = _json_result(content)

    assert event["event_type"] == "card_validated"
    assert event["payload"]["output_pipe"] == "publish"
    assert runtime.get_card(card.id).current_bucket == "done"


@pytest.mark.anyio
async def test_mcp_boundary_source_validates_pydantic_request() -> None:
    runtime = InMemoryCardRuntime()
    create_app(settings=Settings(), runtime=runtime, registry=InMemoryPatchPanelRegistry())
    patch_panel = load_patch_panel(EXAMPLES / "webhook-boundary-patchpanel.yaml")
    runtime.register_patch_panel(patch_panel)

    content = await mcp.call_tool(
        "ghostmesh.boundary_source",
        {
            "patch_panel_id": "webhook_boundary",
            "source_id": "github_issue_source",
            "external_payload": {
                "issue": {
                    "title": "MCP issue",
                    "body": "Created through MCP",
                    "html_url": "https://example.test/issues/1",
                },
                "repository": {"full_name": "ghostmesh/example"},
                "sender": {"login": "worker"},
            },
            "headers": {"X-GitHub-Delivery": "delivery-1"},
            "actor_token": "dev-webhook-token",
        },
    )
    result = _json_result(content)

    assert result["card"]["payload"]["title"] == "MCP issue"
    assert result["deduplication_key"] == "delivery-1"


@pytest.mark.anyio
async def test_mcp_authorization_blocks_anonymous_boundary_call() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="known", type=ParticipantType.AGENT)]
    )
    create_app(
        settings=Settings(authorization_enabled=True),
        runtime=InMemoryCardRuntime(),
        registry=InMemoryPatchPanelRegistry(),
        authorization_service=AuthorizationService(repository),
    )

    with pytest.raises(Exception, match="missing Ghost Mesh participant"):
        await mcp.call_tool(
            "ghostmesh.boundary_source",
            {
                "patch_panel_id": "webhook_boundary",
                "source_id": "github_issue_source",
                "external_payload": {},
            },
        )


def test_cli_mcp_server_entrypoint_runs_stdio(monkeypatch: pytest.MonkeyPatch) -> None:
    from ghostmesh import cli

    called = {}

    def fake_run_stdio() -> None:
        called["stdio"] = True

    monkeypatch.setattr(cli, "run_stdio", fake_run_stdio)

    assert cli.main(["mcp-server"]) == 0
    assert called == {"stdio": True}
