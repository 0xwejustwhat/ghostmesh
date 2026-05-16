from __future__ import annotations

from uuid import UUID

import pytest

from ghostmesh.artifacts import (
    LocalGitArtifactStore,
    S3CompatibleArtifactStore,
    validate_artifact_references,
)
from ghostmesh.domain import AcceptanceContract
from ghostmesh.runtime.errors import InvalidOperationError

CARD_ID = UUID("11111111-1111-1111-1111-111111111111")


def test_local_git_artifact_store_writes_bytes_and_returns_reference(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    store = LocalGitArtifactStore(repo / "artifacts", repo_root=repo)

    artifact = store.put_bytes(
        card_id=CARD_ID,
        data=b"hello",
        filename="draft.txt",
        content_type="text/plain",
        metadata={"role": "draft"},
    )

    assert artifact.storage_ref.startswith("git:working-tree:artifacts/")
    assert artifact.content_hash == (
        "sha256:2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e730"
        "43362938b9824"
    )
    assert artifact.size_bytes == 5


def test_s3_artifact_store_uploads_and_returns_reference() -> None:
    class FakeS3Client:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        def put_object(self, **kwargs: object) -> None:
            self.calls.append(kwargs)

    client = FakeS3Client()
    store = S3CompatibleArtifactStore(bucket="ghostmesh", prefix="artifacts", client=client)

    artifact = store.put_bytes(
        card_id=CARD_ID,
        data=b"video bytes",
        filename="clip.mp4",
        content_type="video/mp4",
        metadata={"role": "preview"},
    )

    assert artifact.storage_ref.startswith(f"s3://ghostmesh/artifacts/{CARD_ID}/")
    assert artifact.content_type == "video/mp4"
    assert client.calls[0]["Bucket"] == "ghostmesh"
    assert client.calls[0]["ContentType"] == "video/mp4"


def test_acceptance_contract_requires_multiple_artifact_references() -> None:
    store = LocalGitArtifactStore("/tmp/ghostmesh-test-artifacts")
    draft = store.put_bytes(
        card_id=CARD_ID,
        data=b"draft",
        filename="draft.txt",
        content_type="text/plain",
        metadata={"role": "draft"},
    )
    contract = AcceptanceContract(
        id="multi",
        description="Needs draft and metrics artifacts.",
        rules=[
            {"type": "artifact_reference_structure"},
            {"type": "required_artifacts", "min_count": 2, "roles": ["draft", "metrics"]},
        ],
    )

    with pytest.raises(InvalidOperationError, match="at least 2"):
        validate_artifact_references([draft], contract)
