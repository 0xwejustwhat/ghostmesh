from __future__ import annotations

from pathlib import Path

import pytest

from ghostmesh.domain import PatchPanel
from ghostmesh.domain.models import NodeType
from ghostmesh.patchpanel import PatchPanelValidator, load_patch_panel
from ghostmesh.patchpanel.errors import PatchPanelValidationError

EXAMPLES = Path(__file__).resolve().parents[1] / "examples" / "patchpanels"


def test_loads_valid_hello_world_patch_panel() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "hello-world-patchpanel.yaml")

    assert patch_panel.id == "hello_world"
    assert {node.type for node in patch_panel.nodes}


def test_explicit_cycle_is_allowed_and_reported() -> None:
    patch_panel = load_patch_panel(EXAMPLES / "cyclic-review-patchpanel.yaml", validate_graph=False)

    report = PatchPanelValidator().validate(patch_panel)

    assert ["review_validator", "draft_worker"] in report.cycles or [
        "draft_worker",
        "review_validator",
    ] in report.cycles


def test_dead_end_non_sink_is_rejected() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source"},
            {"id": "worker", "type": "worker"},
            {"id": "sink", "type": "sink"},
        ],
        edges=[
            {"from": "source", "to": "worker", "on": "card_created"},
        ],
    )

    with pytest.raises(PatchPanelValidationError, match="dead end"):
        PatchPanelValidator().validate(patch_panel)


def test_unreachable_node_is_rejected() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source"},
            {"id": "worker", "type": "worker"},
            {"id": "orphan_worker", "type": "worker"},
            {"id": "sink", "type": "sink"},
        ],
        edges=[
            {"from": "source", "to": "worker", "on": "card_created"},
            {"from": "worker", "to": "sink", "on": "done"},
        ],
    )

    with pytest.raises(PatchPanelValidationError, match="orphan_worker"):
        PatchPanelValidator().validate(patch_panel)


def test_missing_pipe_binding_is_rejected() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source", "output_pipes": ["source_output"]},
            {"id": "sink", "type": "sink"},
        ],
        edges=[
            {"from": "source", "to": "sink", "on": "card_created"},
        ],
    )

    with pytest.raises(PatchPanelValidationError, match="source_output"):
        PatchPanelValidator().validate(patch_panel)


def test_pipe_binding_to_unknown_bucket_is_rejected() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source", "output_pipes": ["source_output"]},
            {"id": "sink", "type": "sink"},
        ],
        pipe_bindings={
            "source_output": {
                "node": "source",
                "direction": "output",
                "bucket": "missing_bucket",
            }
        },
        edges=[
            {"from": "source", "to": "sink", "on": "card_created"},
        ],
    )

    with pytest.raises(PatchPanelValidationError, match="missing_bucket"):
        PatchPanelValidator().validate(patch_panel)


def test_edge_to_unknown_node_is_rejected() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source"},
            {"id": "sink", "type": "sink"},
        ],
        edges=[
            {"from": "source", "to": "missing_node", "on": "card_created"},
        ],
    )

    with pytest.raises(PatchPanelValidationError, match="missing_node"):
        PatchPanelValidator().validate(patch_panel)


def test_source_with_incoming_edge_and_sink_with_outgoing_edge_are_rejected() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source"},
            {"id": "worker", "type": "worker"},
            {"id": "sink", "type": "sink"},
        ],
        edges=[
            {"from": "source", "to": "worker", "on": "card_created"},
            {"from": "worker", "to": "source", "on": "bad_return"},
            {"from": "worker", "to": "sink", "on": "done"},
            {"from": "sink", "to": "worker", "on": "bad_restart"},
        ],
    )

    with pytest.raises(PatchPanelValidationError) as exc_info:
        PatchPanelValidator().validate(patch_panel)

    assert "source node 'source' must not have incoming edges" in str(exc_info.value)
    assert "sink node 'sink' must not have outgoing edges" in str(exc_info.value)


def test_all_core_node_types_can_be_declared() -> None:
    patch_panel = _minimal_patch_panel(
        nodes=[
            {"id": "source", "type": "source"},
            {"id": "worker", "type": "worker"},
            {"id": "validator", "type": "validator"},
            {"id": "junction", "type": "junction"},
            {"id": "learning", "type": "learning"},
            {"id": "subworkflow", "type": "subworkflow"},
            {"id": "sink", "type": "sink"},
        ],
        edges=[
            {"from": "source", "to": "worker", "on": "card_created"},
            {"from": "worker", "to": "validator", "on": "artifact_submitted"},
            {"from": "validator", "to": "junction", "on": "accepted"},
            {"from": "junction", "to": "learning", "on": "routed"},
            {"from": "learning", "to": "subworkflow", "on": "proposal_created"},
            {"from": "subworkflow", "to": "sink", "on": "completed"},
        ],
    )

    PatchPanelValidator().validate(patch_panel)

    assert {node.type for node in patch_panel.nodes} == set(NodeType)


def _minimal_patch_panel(
    *,
    nodes: list[dict[str, object]],
    edges: list[dict[str, object]],
    pipe_bindings: dict[str, dict[str, object]] | None = None,
) -> PatchPanel:
    return PatchPanel.model_validate(
        {
            "id": "test_panel",
            "version": "1.0.0",
            "buckets": [{"id": "bucket"}],
            "nodes": nodes,
            "edges": edges,
            "pipe_bindings": pipe_bindings or {},
        }
    )
