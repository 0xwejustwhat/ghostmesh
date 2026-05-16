from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ghostmesh.domain.authority import PermissionName


class NodeType(StrEnum):
    SOURCE = "source"
    WORKER = "worker"
    VALIDATOR = "validator"
    LEARNING = "learning"
    SINK = "sink"
    SUBWORKFLOW = "subworkflow"


class MutationStatus(StrEnum):
    PROPOSED = "proposed"
    SHADOWING = "shadowing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class PatchPanelRegistryStatus(StrEnum):
    DRAFT = "draft"
    REVIEW = "review"
    APPROVED = "approved"
    PUBLISHED = "published"
    ARCHIVED = "archived"
    SUPERSEDED = "superseded"


class PatchPanelProposalType(StrEnum):
    CREATE = "create"
    MODIFY = "modify"


class PatchPanelProposalStatus(StrEnum):
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROMOTED = "promoted"


class GenesisIntentStatus(StrEnum):
    RECEIVED = "received"
    LAUNCHED = "launched"
    DESIGN_REQUIRED = "design_required"
    PROPOSED = "proposed"


class AcceptanceContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str
    schema_ref: str | None = None
    rules: list[dict[str, Any]] = Field(default_factory=list)


class BucketDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    description: str | None = None
    input_requirements: list[str] = Field(default_factory=list)
    output_requirements: list[str] = Field(default_factory=list)
    acceptance_contract: str | None = None
    shadow_eligible: bool = False


class NodeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: NodeType
    validator_kind: str | None = None
    description: str | None = None
    input_pipes: list[str] = Field(default_factory=list)
    output_pipes: list[str] = Field(default_factory=list)
    acceptance_contract: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class EdgeDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_node: str = Field(alias="from")
    to_node: str = Field(alias="to")
    on: str
    condition: dict[str, Any] | None = None


class PipeBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: str
    node: str | None = None
    direction: str | None = Field(default=None, pattern="^(input|output)$")


class WorkflowVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    patch_panel_id: str
    version: str
    active: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    card_id: UUID
    event_id: UUID | None = None
    storage_ref: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    size_bytes: int = Field(ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Lease(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    card_id: UUID
    node_id: str
    worker_id: str
    input_pipe: str
    claimed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    released_at: datetime | None = None


class CardEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    card_id: UUID
    event_type: str
    actor_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Card(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    workflow_version: str
    current_bucket: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CardLocation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    card_id: UUID
    bucket: str
    status: str = Field(default="active", pattern="^(active|pending|exited)$")
    entered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    accepted_at: datetime | None = None
    exited_at: datetime | None = None


class ValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    card_id: UUID
    validator_id: str
    accepted: bool
    reason: str | None = None
    output_pipe: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ShadowCardLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    production_card_id: UUID
    shadow_card_id: UUID
    candidate_id: str
    status: str = Field(default="active", pattern="^(active|completed|cancelled)$")
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ProposedMutation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    mutation_type: str
    proposed_by: str
    payload: dict[str, Any]
    status: MutationStatus = MutationStatus.PROPOSED
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    validated_at: datetime | None = None
    promoted_at: datetime | None = None


class PatchPanel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    id: str
    version: str
    description: str | None = None
    buckets: list[BucketDefinition]
    nodes: list[NodeDefinition]
    edges: list[EdgeDefinition]
    pipe_bindings: dict[str, PipeBinding] = Field(default_factory=dict)
    acceptance_contracts: list[AcceptanceContract] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_unique_local_ids(self) -> PatchPanel:
        _ensure_unique("bucket", [bucket.id for bucket in self.buckets])
        _ensure_unique("node", [node.id for node in self.nodes])
        _ensure_unique(
            "acceptance contract",
            [contract.id for contract in self.acceptance_contracts],
        )
        return self


class PatchPanelRegistryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_permissions: list[PermissionName] = Field(default_factory=list)
    risk_level: str | None = None
    estimated_cost: str | None = None
    estimated_latency: str | None = None
    owner_participant_id: str | None = None
    status: PatchPanelRegistryStatus = PatchPanelRegistryStatus.DRAFT


class PatchPanelRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    patch_panel_id: str
    version: str
    name: str
    description: str | None = None
    tags: list[str] = Field(default_factory=list)
    input_types: list[str] = Field(default_factory=list)
    output_types: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    required_permissions: list[PermissionName] = Field(default_factory=list)
    risk_level: str | None = None
    estimated_cost: str | None = None
    estimated_latency: str | None = None
    owner_participant_id: str | None = None
    status: PatchPanelRegistryStatus = PatchPanelRegistryStatus.DRAFT
    supersedes_entry_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    archived_at: datetime | None = None

    @classmethod
    def from_patch_panel(
        cls,
        patch_panel: PatchPanel,
        registry_metadata: PatchPanelRegistryMetadata,
        *,
        supersedes_entry_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PatchPanelRegistryEntry:
        return cls(
            patch_panel_id=patch_panel.id,
            version=patch_panel.version,
            name=registry_metadata.name,
            description=registry_metadata.description,
            tags=registry_metadata.tags,
            input_types=registry_metadata.input_types,
            output_types=registry_metadata.output_types,
            required_tools=registry_metadata.required_tools,
            required_permissions=registry_metadata.required_permissions,
            risk_level=registry_metadata.risk_level,
            estimated_cost=registry_metadata.estimated_cost,
            estimated_latency=registry_metadata.estimated_latency,
            owner_participant_id=registry_metadata.owner_participant_id,
            status=registry_metadata.status,
            supersedes_entry_id=supersedes_entry_id,
            metadata=metadata or {},
        )


class PatchPanelValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PatchPanelProposalReviewEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_id: str
    action: str
    reason: str | None = None
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


class PatchPanelProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    proposal_type: PatchPanelProposalType
    proposed_by: str
    base_patch_panel_id: str | None = None
    base_version: str | None = None
    candidate_definition: PatchPanel
    registry_metadata: PatchPanelRegistryMetadata
    validation_report: PatchPanelValidationReport
    status: PatchPanelProposalStatus = PatchPanelProposalStatus.IN_REVIEW
    review_events: list[PatchPanelProposalReviewEvent] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    promoted_registry_entry_id: UUID | None = None


class GenesisIntentConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    risk_level: str | None = None
    max_latency: str | None = None
    requires_human_approval: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class GenesisIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID = Field(default_factory=uuid4)
    requested_by: str
    deduplication_key: str = Field(min_length=1)
    goal: str = Field(min_length=1)
    input_type: str
    desired_outputs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    constraints: GenesisIntentConstraints = Field(default_factory=GenesisIntentConstraints)
    launch_if_existing: bool = True
    propose_if_missing: bool = True
    status: GenesisIntentStatus = GenesisIntentStatus.RECEIVED
    candidate_registry_entry_ids: list[UUID] = Field(default_factory=list)
    selected_registry_entry_id: UUID | None = None
    launched_card_id: UUID | None = None
    proposal_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)


def _ensure_unique(label: str, values: list[str]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        formatted = ", ".join(sorted(duplicates))
        raise ValueError(f"duplicate {label} id(s): {formatted}")
