from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_phase9_public_docs_and_agent_skills_exist() -> None:
    required = [
        "README.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        "LICENSE",
        "ROADMAP.md",
        "docs/architecture.md",
        "docs/api.md",
        "docs/worker-sdk.md",
        "docs/deployment.md",
        "docs/workflows.md",
        "docs/ai-adoption-path.md",
        "docs/skills/README.md",
        "docs/skills/worker/SKILL.md",
        "docs/skills/worker/api.md",
        "docs/skills/worker/mcp.md",
        "docs/skills/worker/examples.md",
        "docs/skills/worker/failure-modes.md",
        "docs/skills/boundary-adapter/SKILL.md",
        "docs/skills/boundary-adapter/source-node.md",
        "docs/skills/boundary-adapter/sink-node.md",
        "docs/skills/boundary-adapter/api.md",
        "docs/skills/boundary-adapter/mcp.md",
        "docs/skills/boundary-adapter/idempotency.md",
        "docs/skills/boundary-adapter/examples.md",
        "docs/skills/validator/SKILL.md",
        "docs/skills/validator/api.md",
        "docs/skills/validator/mcp.md",
        "docs/skills/validator/decision-shapes.md",
        "docs/skills/validator/examples.md",
        "docs/skills/workflow-architect/SKILL.md",
        "docs/skills/workflow-architect/patch-panel-generation.md",
        "docs/skills/workflow-architect/mutation-cards.md",
        "docs/skills/workflow-architect/shadow-lanes.md",
        "docs/skills/workflow-architect/promotion.md",
        "docs/skills/workflow-architect/examples.md",
        "deploy/helm/ghostmesh/Chart.yaml",
    ]

    missing = [path for path in required if not (ROOT / path).exists()]

    assert missing == []


def test_agent_skill_docs_preserve_ghost_mesh_operating_boundaries() -> None:
    worker = (ROOT / "docs/skills/worker/SKILL.md").read_text()
    boundary = (ROOT / "docs/skills/boundary-adapter/SKILL.md").read_text()
    validator = (ROOT / "docs/skills/validator/SKILL.md").read_text()
    architect = (ROOT / "docs/skills/workflow-architect/SKILL.md").read_text()

    assert "Ghost Mesh is not your orchestrator" in worker
    assert "pipe-aware, not graph-aware" in worker
    assert "Do not route Cards" in worker
    assert "deduplication" in boundary
    assert "egress idempotency key" in boundary
    assert "Acceptance Contract" in validator
    assert "Do not embed routing decisions inside Worker Nodes" in architect
    assert "shadow evaluation and promotion gates" in architect


def test_agent_skill_docs_include_executable_interface_details() -> None:
    skill_paths = [
        ROOT / "docs/skills/worker/SKILL.md",
        ROOT / "docs/skills/boundary-adapter/SKILL.md",
        ROOT / "docs/skills/validator/SKILL.md",
        ROOT / "docs/skills/workflow-architect/SKILL.md",
    ]

    for path in skill_paths:
        text = path.read_text()
        assert "Required Inputs" in text
        assert "MCP" in text
        assert "REST" in text
        assert "```json" in text

    worker = (ROOT / "docs/skills/worker/SKILL.md").read_text()
    boundary = (ROOT / "docs/skills/boundary-adapter/SKILL.md").read_text()
    validator = (ROOT / "docs/skills/validator/SKILL.md").read_text()

    assert "POST /cards/claim" in worker
    assert "POST /cards/submit" in worker
    assert "Idempotency-Key" in worker
    assert "POST /boundaries/source" in boundary
    assert "POST /boundaries/sink" in boundary
    assert "egress_idempotency_key" in boundary
    assert "POST /validators/<validator_id>/cards/<card_id>/decision" in validator
