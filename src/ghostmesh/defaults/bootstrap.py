from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ghostmesh.domain import (
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
)
from ghostmesh.patchpanel import load_patch_panel
from ghostmesh.registry import PatchPanelRegistry, PatchPanelRegistrySearch
from ghostmesh.runtime import CardRuntime


@dataclass(frozen=True)
class BootstrapResult:
    patch_panel_id: str
    version: str
    registered_runtime: bool
    registered_registry: bool


class SystemWorkflowBootstrapper:
    """Idempotently load configured system Patch Panels into runtime and registry."""

    def __init__(
        self,
        *,
        runtime: CardRuntime,
        registry: PatchPanelRegistry,
        patch_panel_paths: tuple[str, ...],
    ) -> None:
        self.runtime = runtime
        self.registry = registry
        self.patch_panel_paths = patch_panel_paths

    def bootstrap(self) -> list[BootstrapResult]:
        results: list[BootstrapResult] = []
        for configured_path in self.patch_panel_paths:
            path = _resolve_path(configured_path)
            patch_panel = load_patch_panel(path)
            runtime_registered = any(
                existing.id == patch_panel.id and existing.version == patch_panel.version
                for existing in self.runtime.list_patch_panels()
            )
            if not runtime_registered:
                self.runtime.register_patch_panel(patch_panel)

            registry_registered = any(
                entry.patch_panel_id == patch_panel.id and entry.version == patch_panel.version
                for entry in self.registry.search(
                    PatchPanelRegistrySearch(include_archived=True, include_superseded=True)
                )
            )
            if not registry_registered:
                metadata = _registry_metadata_for(patch_panel.metadata.get("registry"))
                entry = PatchPanelRegistryEntry.from_patch_panel(
                    patch_panel,
                    metadata,
                    metadata={"system_workflow": True, "source_path": str(path)},
                )
                self.registry.register(entry)

            results.append(
                BootstrapResult(
                    patch_panel_id=patch_panel.id,
                    version=patch_panel.version,
                    registered_runtime=not runtime_registered,
                    registered_registry=not registry_registered,
                )
            )
        return results


def _registry_metadata_for(raw: object) -> PatchPanelRegistryMetadata:
    if isinstance(raw, dict):
        return PatchPanelRegistryMetadata.model_validate(
            {"status": PatchPanelRegistryStatus.PUBLISHED, **raw}
        )
    return PatchPanelRegistryMetadata(
        name="System Patch Panel Approval",
        description="System workflow for Patch Panel proposal validation and governance.",
        tags=["system", "governance", "patch-panel-approval"],
        input_types=["patch_panel_proposal"],
        output_types=["patch_panel_registry_entry"],
        risk_level="medium",
        status=PatchPanelRegistryStatus.PUBLISHED,
    )


def _resolve_path(configured_path: str) -> Path:
    path = Path(configured_path)
    if path.exists() or path.is_absolute():
        return path
    packaged_default = Path(__file__).parent / "patchpanels" / path.name
    if packaged_default.exists():
        return packaged_default
    return path
