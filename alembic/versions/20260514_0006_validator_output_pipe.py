"""add explicit validator output pipe

Revision ID: 20260514_0006
Revises: 20260514_0005
Create Date: 2026-05-14 00:06:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260514_0006"
down_revision: str | None = "20260514_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("validation_results", sa.Column("output_pipe", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("validation_results", "output_pipe")
