from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
)
from sqlalchemy.sql.schema import Column

metadata = MetaData()

patch_panels = Table(
    "patch_panels",
    metadata,
    Column("id", String, primary_key=True),
    Column("version", String, primary_key=True),
    Column("definition", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

participants = Table(
    "participants",
    metadata,
    Column("id", String, primary_key=True),
    Column("type", String, nullable=False),
    Column("display_name", String, nullable=True),
    Column("status", String, nullable=False),
    Column("trust_level", String, nullable=True),
    Column("auth_method", String, nullable=True),
    Column("participant_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("archived_at", DateTime(timezone=True), nullable=True),
)

roles = Table(
    "roles",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False, unique=True),
    Column("description", Text, nullable=True),
    Column("role_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

participant_roles = Table(
    "participant_roles",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=False),
    Column("role_id", String, ForeignKey("roles.id"), nullable=False),
    Column("scope_type", String, nullable=False),
    Column("scope_id", String, nullable=True),
    Column("assigned_by", String, ForeignKey("participants.id"), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("assignment_metadata", JSON, nullable=False),
)

permission_grants = Table(
    "permission_grants",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("role_id", String, ForeignKey("roles.id"), nullable=True),
    Column("permission", String, nullable=False),
    Column("scope_type", String, nullable=False),
    Column("scope_id", String, nullable=True),
    Column("granted_by", String, ForeignKey("participants.id"), nullable=True),
    Column("expires_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    Column("grant_metadata", JSON, nullable=False),
    CheckConstraint(
        "(participant_id IS NOT NULL AND role_id IS NULL) "
        "OR (participant_id IS NULL AND role_id IS NOT NULL)",
        name="ck_permission_grants_one_target",
    ),
)

authorization_audit_events = Table(
    "authorization_audit_events",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("action", String, nullable=False),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("permission", String, nullable=True),
    Column("scope_type", String, nullable=True),
    Column("scope_id", String, nullable=True),
    Column("allowed", Boolean, nullable=True),
    Column("reason", Text, nullable=True),
    Column("request_ref", Text, nullable=True),
    Column("target_ref", Text, nullable=True),
    Column("event_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

patch_panel_registry_entries = Table(
    "patch_panel_registry_entries",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("patch_panel_id", String, nullable=False),
    Column("version", String, nullable=False),
    Column("name", String, nullable=False),
    Column("description", Text, nullable=True),
    Column("tags", JSON, nullable=False),
    Column("input_types", JSON, nullable=False),
    Column("output_types", JSON, nullable=False),
    Column("required_tools", JSON, nullable=False),
    Column("required_permissions", JSON, nullable=False),
    Column("risk_level", String, nullable=True),
    Column("estimated_cost", String, nullable=True),
    Column("estimated_latency", String, nullable=True),
    Column("owner_participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("status", String, nullable=False),
    Column(
        "supersedes_entry_id",
        Uuid(as_uuid=True),
        ForeignKey("patch_panel_registry_entries.id"),
        nullable=True,
    ),
    Column("registry_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("archived_at", DateTime(timezone=True), nullable=True),
)

workflow_versions = Table(
    "workflow_versions",
    metadata,
    Column("id", String, primary_key=True),
    Column("patch_panel_id", String, nullable=False),
    Column("version", String, nullable=False),
    Column("active", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

buckets = Table(
    "buckets",
    metadata,
    Column("workflow_version", String, ForeignKey("workflow_versions.id"), primary_key=True),
    Column("id", String, primary_key=True),
    Column("definition", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

cards = Table(
    "cards",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("workflow_version", String, nullable=False),
    Column("current_bucket", String, nullable=False),
    Column("payload", JSON, nullable=False),
    Column("card_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

card_locations = Table(
    "card_locations",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("bucket", String, nullable=False),
    Column("status", String, nullable=False),
    Column("entered_at", DateTime(timezone=True), nullable=False),
    Column("accepted_at", DateTime(timezone=True), nullable=True),
    Column("exited_at", DateTime(timezone=True), nullable=True),
)

leases = Table(
    "leases",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("node_id", String, nullable=False),
    Column("worker_id", String, nullable=False),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("input_pipe", String, nullable=False),
    Column("claimed_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("released_at", DateTime(timezone=True), nullable=True),
)

validation_results = Table(
    "validation_results",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("validator_id", String, nullable=False),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("accepted", Boolean, nullable=False),
    Column("reason", Text, nullable=True),
    Column("output_pipe", String, nullable=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

artifacts = Table(
    "artifacts",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("event_id", Uuid(as_uuid=True), nullable=True),
    Column("storage_ref", Text, nullable=False),
    Column("content_hash", String, nullable=False),
    Column("content_type", String, nullable=False),
    Column("size_bytes", Integer, nullable=False),
    Column("artifact_metadata", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

card_events = Table(
    "card_events",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("event_type", String, nullable=False),
    Column("actor_id", String, nullable=True),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
)

idempotency_records = Table(
    "idempotency_records",
    metadata,
    Column("key", String, primary_key=True),
    Column("operation", String, nullable=False),
    Column("response_ref", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

shadow_card_links = Table(
    "shadow_card_links",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("production_card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("shadow_card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("candidate_id", String, nullable=False),
    Column("status", String, nullable=False),
    Column("metrics", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

proposed_mutations = Table(
    "proposed_mutations",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("mutation_type", String, nullable=False),
    Column("proposed_by", String, nullable=False),
    Column("participant_id", String, ForeignKey("participants.id"), nullable=True),
    Column("payload", JSON, nullable=False),
    Column("status", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("validated_at", DateTime(timezone=True), nullable=True),
    Column("promoted_at", DateTime(timezone=True), nullable=True),
)
