from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeType(StrEnum):
    SOURCE = "source"
    WORKER = "worker"
    VALIDATOR = "validator"
    JUNCTION = "junction"
    LEARNING = "learning"
    SINK = "sink"
    SUBWORKFLOW = "subworkflow"


class MutationStatus(StrEnum):
    PROPOSED = "proposed"
    SHADOWING = "shadowing"
    VALIDATED = "validated"
    REJECTED = "rejected"
    PROMOTED = "promoted"


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
