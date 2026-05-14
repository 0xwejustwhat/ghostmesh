from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, MetaData, String, Table, Text, Uuid
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
    Column("accepted", Boolean, nullable=False),
    Column("reason", Text, nullable=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

artifacts = Table(
    "artifacts",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("node_id", String, nullable=False),
    Column("worker_id", String, nullable=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

card_events = Table(
    "card_events",
    metadata,
    Column("id", Uuid(as_uuid=True), primary_key=True),
    Column("card_id", Uuid(as_uuid=True), ForeignKey("cards.id"), nullable=False),
    Column("event_type", String, nullable=False),
    Column("actor_id", String, nullable=True),
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
    Column("payload", JSON, nullable=False),
    Column("status", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("validated_at", DateTime(timezone=True), nullable=True),
    Column("promoted_at", DateTime(timezone=True), nullable=True),
)
