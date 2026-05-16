from __future__ import annotations

from uuid import UUID

from ghostmesh.domain import ArtifactReference


def artifact_ref(card_id: str | UUID, *, role: str = "draft") -> ArtifactReference:
    card_uuid = UUID(str(card_id))
    return ArtifactReference(
        card_id=card_uuid,
        storage_ref=f"git:working-tree:artifacts/{card_uuid}/{role}.txt",
        content_hash="sha256:" + ("a" * 64),
        content_type="text/plain",
        size_bytes=12,
        metadata={"role": role},
    )
