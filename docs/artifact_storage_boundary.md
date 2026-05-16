# Artifact Storage Boundary

## Rule

Postgres is an accountability and routing index. It stores artifact references and metadata only. It must not store artifact content, large file bodies, worker output payloads, media, datasets, or generated deliverables.

## Runtime Contract

Workers upload artifacts to an external store first, then submit one or more `ArtifactReference` records to Ghost Mesh.

Each reference includes:

- `id`
- `card_id`
- `event_id`, assigned by the runtime when accepted
- `storage_ref`, such as `git:working-tree:artifacts/card/file.txt` or `s3://bucket/key`
- `content_hash`, using `sha256:<hex>`
- `content_type`
- `size_bytes`
- metadata such as `role`, `model`, `cost`, `latency`, or provenance
- `created_at`

The evidence trail may include artifact IDs, storage references, hashes, content types, sizes, and metadata. It must not include content bodies.

## Storage Backends

The MVP includes two pluggable stores:

- `LocalGitArtifactStore`: writes bytes to local disk and returns Git working-tree references when the artifact root is inside a Git repository. This is intended for local development and version-controlled text or mixed outputs. Git LFS can be layered underneath the repository for larger tracked files.
- `S3CompatibleArtifactStore`: uploads bytes through a boto3-compatible client and returns `s3://bucket/key` references. This is intended for S3, MinIO, and production binary/media storage.

Workers may use either store directly or bring their own implementation that returns valid `ArtifactReference` objects.

## Database Boundary

The `artifacts` table stores:

- `id`
- `card_id`
- `event_id`
- `storage_ref`
- `content_hash`
- `content_type`
- `size_bytes`
- `artifact_metadata`
- `created_at`

It does not store `payload`, `content`, blobs, JSON output bodies, or files.

## Migration Path

Migration `20260514_0004` adds reference-only columns, backfills any legacy rows with `legacy-postgres-artifact:<id>` references, marks them with `artifact_metadata.requires_manual_rehydration = true`, and removes the legacy `payload`, `node_id`, and `worker_id` columns.

If a deployed environment has legacy artifact payload rows, operators should export those payloads before applying the migration, upload them into the chosen artifact store, and replace the generated legacy references with real `git:` or `s3://` references and sha256 hashes.

## Acceptance Contracts

Patch Panel acceptance contracts can require artifact reference structure and multiple artifacts by role:

```yaml
rules:
  - type: artifact_reference_structure
  - type: required_artifacts
    min_count: 2
    roles:
      - draft
      - metrics
```

This keeps validation explicit while allowing workers to submit bundles such as a generated draft, a QA report, and a cost/latency summary without placing any content in Postgres.
