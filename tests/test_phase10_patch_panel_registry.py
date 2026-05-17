from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from ghostmesh.api.main import create_app
from ghostmesh.auth import AuthorizationService, InMemoryAuthorizationRepository
from ghostmesh.config import Settings
from ghostmesh.domain import (
    Participant,
    ParticipantType,
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionGrant,
    PermissionName,
    Scope,
    ScopeType,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.persistence.tables import metadata
from ghostmesh.registry import (
    InMemoryPatchPanelRegistry,
    PatchPanelRegistrySearch,
    PostgresPatchPanelRegistry,
)
from ghostmesh.runtime import InMemoryCardRuntime

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def registry_metadata(*, status: PatchPanelRegistryStatus) -> PatchPanelRegistryMetadata:
    return PatchPanelRegistryMetadata(
        name="Hello World",
        description="A searchable workflow",
        tags=["example", "review"],
        input_types=["brief"],
        output_types=["approved_artifact"],
        required_tools=["artifact_store"],
        required_permissions=[PermissionName.CARD_CREATE, PermissionName.CARD_CLAIM],
        risk_level="low",
        estimated_cost="low",
        estimated_latency="minutes",
        owner_participant_id="owner-1",
        status=status,
    )


def test_registry_entry_model_is_serializable_and_separate_from_patch_panel_definition() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    entry = PatchPanelRegistryEntry.from_patch_panel(
        patch_panel,
        registry_metadata(status=PatchPanelRegistryStatus.PUBLISHED),
        metadata={"source": "test"},
    )

    dumped = entry.model_dump(mode="json")

    assert dumped["patch_panel_id"] == "hello_world"
    assert dumped["status"] == "published"
    assert dumped["required_permissions"] == ["card:create", "card:claim"]
    assert "buckets" not in dumped
    assert "payload" not in dumped


def test_registry_exact_search_excludes_archived_and_superseded_by_default() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    published = PatchPanelRegistryEntry.from_patch_panel(
        patch_panel,
        registry_metadata(status=PatchPanelRegistryStatus.PUBLISHED),
    )
    archived = PatchPanelRegistryEntry.from_patch_panel(
        patch_panel,
        registry_metadata(status=PatchPanelRegistryStatus.ARCHIVED),
    )
    superseded = PatchPanelRegistryEntry.from_patch_panel(
        patch_panel,
        registry_metadata(status=PatchPanelRegistryStatus.SUPERSEDED),
    )
    registry = InMemoryPatchPanelRegistry([published, archived, superseded])

    default_results = registry.search(PatchPanelRegistrySearch(tag="example"))
    inclusive_results = registry.search(
        PatchPanelRegistrySearch(
            tag="example",
            include_archived=True,
            include_superseded=True,
        )
    )

    assert [entry.id for entry in default_results] == [published.id]
    assert {entry.id for entry in inclusive_results} == {published.id, archived.id, superseded.id}
    assert registry.search(PatchPanelRegistrySearch(input_type="brief")) == [published]
    assert registry.search(PatchPanelRegistrySearch(output_type="approved_artifact")) == [published]
    assert registry.search(PatchPanelRegistrySearch(required_tool="artifact_store")) == [published]
    assert registry.search(PatchPanelRegistrySearch(risk_level="low")) == [published]
    assert registry.search(PatchPanelRegistrySearch(owner_participant_id="owner-1")) == [published]


def test_registry_api_supports_authorized_registration_and_discovery() -> None:
    repository = InMemoryAuthorizationRepository(
        participants=[Participant(id="designer", type=ParticipantType.AGENT)],
        permission_grants=[
            PermissionGrant(
                participant_id="designer",
                permission=PermissionName.PATCH_PANEL_CREATE,
                scope=Scope(type=ScopeType.PATCH_PANEL, id="hello_world"),
            ),
            PermissionGrant(
                participant_id="designer",
                permission=PermissionName.PATCH_PANEL_DISCOVER,
                scope=Scope.development_global(),
            ),
        ],
    )
    registry = InMemoryPatchPanelRegistry()
    runtime = InMemoryCardRuntime()
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=runtime,
            registry=registry,
            authorization_service=AuthorizationService(repository),
        )
    )
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    create_response = client.post(
        "/registry/patchpanels",
        json={
            "patch_panel": patch_panel.model_dump(mode="json"),
            "registry_metadata": registry_metadata(
                status=PatchPanelRegistryStatus.PUBLISHED
            ).model_dump(mode="json"),
            "metadata": {"source": "api-test"},
        },
        headers={"X-Ghostmesh-Participant": "designer"},
    )
    search_response = client.get(
        "/registry/patchpanels?tag=example&input_type=brief",
        headers={"X-Ghostmesh-Participant": "designer"},
    )

    assert create_response.status_code == 200, create_response.text
    assert search_response.status_code == 200, search_response.text
    assert search_response.json()[0]["name"] == "Hello World"
    assert any(patch_panel.id == "hello_world" for patch_panel in runtime.list_patch_panels())
    assert repository.audit_events[-1].allowed is True


def test_registry_api_requires_discover_permission() -> None:
    client = TestClient(
        create_app(
            settings=Settings(authorization_enabled=True),
            runtime=InMemoryCardRuntime(),
            registry=InMemoryPatchPanelRegistry(),
            authorization_service=AuthorizationService(InMemoryAuthorizationRepository()),
        )
    )

    response = client.get("/registry/patchpanels?tag=example")

    assert response.status_code == 403
    assert response.json() == {"detail": "missing Ghost Mesh participant"}


def test_postgres_registry_persists_search_archive_and_supersede() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata.create_all(engine)
    registry = PostgresPatchPanelRegistry(engine)
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")
    entry = registry.register(
        PatchPanelRegistryEntry.from_patch_panel(
            patch_panel,
            registry_metadata(status=PatchPanelRegistryStatus.PUBLISHED),
        )
    )
    replacement_id = uuid4()

    assert registry.search(PatchPanelRegistrySearch(tag="review"))[0].id == entry.id

    superseded = registry.supersede(entry.id, replacement_id)
    default_results = registry.search(PatchPanelRegistrySearch(tag="review"))
    inclusive_results = registry.search(
        PatchPanelRegistrySearch(tag="review", include_superseded=True)
    )

    assert superseded.status == PatchPanelRegistryStatus.SUPERSEDED
    assert superseded.supersedes_entry_id == replacement_id
    assert default_results == []
    assert inclusive_results[0].id == entry.id
