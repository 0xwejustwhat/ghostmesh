"""add phase 6 shadow and mutation tables

Revision ID: 20260514_0003
Revises: 20260514_0002
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260514_0003"
down_revision: str | None = "20260514_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shadow_card_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("production_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("shadow_card_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["production_card_id"], ["cards.id"]),
        sa.ForeignKeyConstraint(["shadow_card_id"], ["cards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "proposed_mutations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mutation_type", sa.String(), nullable=False),
        sa.Column("proposed_by", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("promoted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("proposed_mutations")
    op.drop_table("shadow_card_links")
