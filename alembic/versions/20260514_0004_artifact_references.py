"""store artifact references instead of payload content

Revision ID: 20260514_0004
Revises: 20260514_0003
Create Date: 2026-05-14 00:04:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260514_0004"
down_revision: str | None = "20260514_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEGACY_HASH = "sha256:" + ("0" * 64)


def upgrade() -> None:
    op.add_column("artifacts", sa.Column("event_id", sa.Uuid(), nullable=True))
    op.add_column("artifacts", sa.Column("storage_ref", sa.Text(), nullable=True))
    op.add_column("artifacts", sa.Column("content_hash", sa.String(), nullable=True))
    op.add_column("artifacts", sa.Column("content_type", sa.String(), nullable=True))
    op.add_column("artifacts", sa.Column("size_bytes", sa.Integer(), nullable=True))
    op.add_column("artifacts", sa.Column("artifact_metadata", sa.JSON(), nullable=True))

    artifacts = sa.table(
        "artifacts",
        sa.column("id", sa.Uuid()),
        sa.column("storage_ref", sa.Text()),
        sa.column("content_hash", sa.String()),
        sa.column("content_type", sa.String()),
        sa.column("size_bytes", sa.Integer()),
        sa.column("artifact_metadata", sa.JSON()),
    )
    op.execute(
        artifacts.update().values(
            storage_ref=sa.text("'legacy-postgres-artifact:' || id::text"),
            content_hash=LEGACY_HASH,
            content_type="application/json",
            size_bytes=0,
            artifact_metadata=sa.text(
                '\'{"migration":"legacy_payload_removed", '
                '"requires_manual_rehydration":true}\'::json'
            ),
        )
    )

    op.alter_column("artifacts", "storage_ref", nullable=False)
    op.alter_column("artifacts", "content_hash", nullable=False)
    op.alter_column("artifacts", "content_type", nullable=False)
    op.alter_column("artifacts", "size_bytes", nullable=False)
    op.alter_column("artifacts", "artifact_metadata", nullable=False)
    op.drop_column("artifacts", "payload")
    op.drop_column("artifacts", "node_id")
    op.drop_column("artifacts", "worker_id")


def downgrade() -> None:
    op.add_column("artifacts", sa.Column("worker_id", sa.String(), nullable=True))
    op.add_column("artifacts", sa.Column("node_id", sa.String(), nullable=True))
    op.add_column("artifacts", sa.Column("payload", sa.JSON(), nullable=True))
    op.execute("UPDATE artifacts SET payload = '{}'::json, node_id = 'legacy_external_store'")
    op.alter_column("artifacts", "payload", nullable=False)
    op.alter_column("artifacts", "node_id", nullable=False)
    op.drop_column("artifacts", "artifact_metadata")
    op.drop_column("artifacts", "size_bytes")
    op.drop_column("artifacts", "content_type")
    op.drop_column("artifacts", "content_hash")
    op.drop_column("artifacts", "storage_ref")
    op.drop_column("artifacts", "event_id")
