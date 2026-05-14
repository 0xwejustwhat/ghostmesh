from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from ghostmesh.domain import PatchPanel
from ghostmesh.patchpanel.errors import PatchPanelLoadError
from ghostmesh.patchpanel.validator import PatchPanelValidator


def load_patch_panel(path: str | Path, *, validate_graph: bool = True) -> PatchPanel:
    patch_panel_path = Path(path)
    raw = _load_mapping(patch_panel_path)

    try:
        patch_panel = PatchPanel.model_validate(raw)
    except ValidationError as exc:
        raise PatchPanelLoadError(f"{patch_panel_path}: schema validation failed: {exc}") from exc

    if validate_graph:
        PatchPanelValidator().validate(patch_panel)

    return patch_panel


def _load_mapping(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise PatchPanelLoadError(f"{path}: file does not exist")

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise PatchPanelLoadError(f"{path}: could not read file: {exc}") from exc

    try:
        if path.suffix.lower() == ".json":
            data = json.loads(text)
        elif path.suffix.lower() in {".yaml", ".yml"}:
            data = yaml.safe_load(text)
        else:
            raise PatchPanelLoadError(f"{path}: unsupported Patch Panel file type")
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise PatchPanelLoadError(f"{path}: could not parse Patch Panel: {exc}") from exc

    if not isinstance(data, dict):
        raise PatchPanelLoadError(f"{path}: Patch Panel root must be a mapping")

    return _normalize_yaml_keys(data)


def _normalize_yaml_keys(data: dict[str, Any]) -> dict[str, Any]:
    # PyYAML follows YAML 1.1 boolean parsing, where an unquoted `on` key becomes True.
    # Patch Panels use `on` as the natural edge event key, so normalize it at the boundary.
    edges = data.get("edges")
    if not isinstance(edges, list):
        return data

    for edge in edges:
        if isinstance(edge, dict) and True in edge and "on" not in edge:
            edge["on"] = edge.pop(True)

    return data
