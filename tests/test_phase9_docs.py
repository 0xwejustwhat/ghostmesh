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
        "docs/skills/worker-skills.md",
        "docs/skills/boundary-adapter-skills.md",
        "docs/skills/validator-skills.md",
        "docs/skills/workflow-architect-skills.md",
        "deploy/helm/ghostmesh/Chart.yaml",
    ]

    missing = [path for path in required if not (ROOT / path).exists()]

    assert missing == []


def test_agent_skill_docs_preserve_ghost_mesh_operating_boundaries() -> None:
    worker = (ROOT / "docs/skills/worker-skills.md").read_text()
    boundary = (ROOT / "docs/skills/boundary-adapter-skills.md").read_text()
    validator = (ROOT / "docs/skills/validator-skills.md").read_text()
    architect = (ROOT / "docs/skills/workflow-architect-skills.md").read_text()

    assert "Ghost Mesh is not your orchestrator" in worker
    assert "pipe-aware, not graph-aware" in worker
    assert "Do not route Cards" in worker
    assert "deduplication" in boundary
    assert "egress idempotency key" in boundary
    assert "Acceptance Contract" in validator
    assert "Do not embed routing decisions inside Worker Nodes" in architect
    assert "shadow evaluation and promotion gates" in architect
