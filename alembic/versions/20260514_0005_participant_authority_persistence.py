"""add participant authority persistence tables

Revision ID: 20260514_0005
Revises: 20260514_0004
Create Date: 2026-05-14 00:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260514_0005"
down_revision: str | None = "20260514_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("type", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("trust_level", sa.String(), nullable=True),
        sa.Column("auth_method", sa.String(), nullable=True),
        sa.Column("participant_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "roles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "participant_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=False),
        sa.Column("role_id", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("assigned_by", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assignment_metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["assigned_by"], ["participants.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "permission_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=True),
        sa.Column("role_id", sa.String(), nullable=True),
        sa.Column("permission", sa.String(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("granted_by", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("grant_metadata", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "(participant_id IS NOT NULL AND role_id IS NULL) "
            "OR (participant_id IS NULL AND role_id IS NOT NULL)",
            name="ck_permission_grants_one_target",
        ),
        sa.ForeignKeyConstraint(["granted_by"], ["participants.id"]),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "authorization_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("participant_id", sa.String(), nullable=True),
        sa.Column("permission", sa.String(), nullable=True),
        sa.Column("scope_type", sa.String(), nullable=True),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("allowed", sa.Boolean(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("request_ref", sa.Text(), nullable=True),
        sa.Column("target_ref", sa.Text(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["participant_id"], ["participants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "patch_panel_registry_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("patch_panel_id", sa.String(), nullable=False),
        sa.Column("version", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("input_types", sa.JSON(), nullable=False),
        sa.Column("output_types", sa.JSON(), nullable=False),
        sa.Column("required_tools", sa.JSON(), nullable=False),
        sa.Column("required_permissions", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(), nullable=True),
        sa.Column("estimated_cost", sa.String(), nullable=True),
        sa.Column("estimated_latency", sa.String(), nullable=True),
        sa.Column("owner_participant_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("supersedes_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("registry_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_participant_id"], ["participants.id"]),
        sa.ForeignKeyConstraint(["supersedes_entry_id"], ["patch_panel_registry_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.add_column("leases", sa.Column("participant_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_leases_participant_id_participants",
        "leases",
        "participants",
        ["participant_id"],
        ["id"],
    )
    op.add_column("validation_results", sa.Column("participant_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_validation_results_participant_id_participants",
        "validation_results",
        "participants",
        ["participant_id"],
        ["id"],
    )
    op.add_column("card_events", sa.Column("participant_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_card_events_participant_id_participants",
        "card_events",
        "participants",
        ["participant_id"],
        ["id"],
    )
    op.add_column("proposed_mutations", sa.Column("participant_id", sa.String(), nullable=True))
    op.create_foreign_key(
        "fk_proposed_mutations_participant_id_participants",
        "proposed_mutations",
        "participants",
        ["participant_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_proposed_mutations_participant_id_participants",
        "proposed_mutations",
        type_="foreignkey",
    )
    op.drop_column("proposed_mutations", "participant_id")
    op.drop_constraint(
        "fk_card_events_participant_id_participants",
        "card_events",
        type_="foreignkey",
    )
    op.drop_column("card_events", "participant_id")
    op.drop_constraint(
        "fk_validation_results_participant_id_participants",
        "validation_results",
        type_="foreignkey",
    )
    op.drop_column("validation_results", "participant_id")
    op.drop_constraint(
        "fk_leases_participant_id_participants",
        "leases",
        type_="foreignkey",
    )
    op.drop_column("leases", "participant_id")

    op.drop_table("patch_panel_registry_entries")
    op.drop_table("authorization_audit_events")
    op.drop_table("permission_grants")
    op.drop_table("participant_roles")
    op.drop_table("roles")
    op.drop_table("participants")
