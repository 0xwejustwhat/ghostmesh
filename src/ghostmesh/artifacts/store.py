from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from ghostmesh.domain import ArtifactReference


class ArtifactStore(Protocol):
    """Uploads bytes and returns an accountability-only artifact reference."""

    def put_bytes(
        self,
        *,
        card_id: UUID,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactReference: ...


class LocalGitArtifactStore:
    """Local filesystem store with Git working-tree references for dev workflows."""

    def __init__(self, root: str | Path, *, repo_root: str | Path | None = None) -> None:
        self.root = Path(root)
        self.repo_root = Path(repo_root).resolve() if repo_root else _discover_git_root(self.root)

    def put_bytes(
        self,
        *,
        card_id: UUID,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactReference:
        artifact_id = uuid4()
        safe_name = Path(filename).name or "artifact.bin"
        path = self.root / str(card_id) / f"{artifact_id}-{safe_name}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return ArtifactReference(
            id=artifact_id,
            card_id=card_id,
            storage_ref=self._storage_ref(path),
            content_hash=_sha256(data),
            content_type=content_type,
            size_bytes=len(data),
            metadata=metadata or {},
        )

    def _storage_ref(self, path: Path) -> str:
        resolved = path.resolve()
        if self.repo_root:
            try:
                rel_path = resolved.relative_to(self.repo_root)
            except ValueError:
                return resolved.as_uri()
            return f"git:working-tree:{rel_path.as_posix()}"
        return resolved.as_uri()


class S3CompatibleArtifactStore:
    """S3/MinIO-compatible store.

    A boto3-compatible client can be injected in tests or production. If no
    client is provided, boto3 is imported lazily so the core runtime stays small.
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "ghostmesh/artifacts",
        client: Any | None = None,
    ) -> None:
        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = client or _boto3_client()

    def put_bytes(
        self,
        *,
        card_id: UUID,
        data: bytes,
        filename: str,
        content_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> ArtifactReference:
        artifact_id = uuid4()
        safe_name = Path(filename).name or "artifact.bin"
        key = f"{self.prefix}/{card_id}/{artifact_id}-{safe_name}"
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            Metadata={k: str(v) for k, v in (metadata or {}).items()},
        )
        return ArtifactReference(
            id=artifact_id,
            card_id=card_id,
            storage_ref=f"s3://{self.bucket}/{key}",
            content_hash=_sha256(data),
            content_type=content_type,
            size_bytes=len(data),
            metadata=metadata or {},
        )


def _sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _discover_git_root(path: Path) -> Path | None:
    current = path.resolve()
    for candidate in [current, *current.parents]:
        if (candidate / ".git").exists():
            return candidate
    return None


def _boto3_client() -> Any:
    try:
        import boto3
    except ImportError as exc:
        raise RuntimeError(
            "boto3 is required for S3CompatibleArtifactStore unless a client is injected"
        ) from exc
    return boto3.client("s3")
