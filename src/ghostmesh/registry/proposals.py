from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from ghostmesh.domain import (
    PatchPanel,
    PatchPanelProposal,
    PatchPanelProposalReviewEvent,
    PatchPanelProposalStatus,
    PatchPanelProposalType,
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PatchPanelValidationReport,
)
from ghostmesh.patchpanel import PatchPanelValidator
from ghostmesh.patchpanel.errors import PatchPanelValidationError
from ghostmesh.registry.service import PatchPanelRegistry
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError, NotFoundError
from ghostmesh.runtime.service import CardRuntime


class PatchPanelProposalStore(Protocol):
    def create(
        self,
        *,
        proposal_type: PatchPanelProposalType,
        proposed_by: str,
        candidate_definition: PatchPanel,
        registry_metadata: PatchPanelRegistryMetadata,
        base_patch_panel_id: str | None = None,
        base_version: str | None = None,
    ) -> PatchPanelProposal: ...

    def get(self, proposal_id: UUID) -> PatchPanelProposal: ...

    def approve(
        self,
        *,
        proposal_id: UUID,
        reviewer_id: str,
        runtime: CardRuntime,
        registry: PatchPanelRegistry,
        reason: str | None = None,
    ) -> PatchPanelProposal: ...

    def reject(
        self,
        *,
        proposal_id: UUID,
        reviewer_id: str,
        reason: str,
    ) -> PatchPanelProposal: ...


class InMemoryPatchPanelProposalStore:
    def __init__(self) -> None:
        self.proposals: dict[UUID, PatchPanelProposal] = {}

    def create(
        self,
        *,
        proposal_type: PatchPanelProposalType,
        proposed_by: str,
        candidate_definition: PatchPanel,
        registry_metadata: PatchPanelRegistryMetadata,
        base_patch_panel_id: str | None = None,
        base_version: str | None = None,
    ) -> PatchPanelProposal:
        validation_report = _validate_candidate(candidate_definition)
        proposal = PatchPanelProposal(
            proposal_type=proposal_type,
            proposed_by=proposed_by,
            base_patch_panel_id=base_patch_panel_id,
            base_version=base_version,
            candidate_definition=candidate_definition,
            registry_metadata=registry_metadata,
            validation_report=validation_report,
            review_events=[
                PatchPanelProposalReviewEvent(
                    actor_id=proposed_by,
                    action="submitted",
                    metadata={"validation": "passed"},
                )
            ],
        )
        self.proposals[proposal.id] = proposal
        return proposal

    def get(self, proposal_id: UUID) -> PatchPanelProposal:
        try:
            return self.proposals[proposal_id]
        except KeyError as exc:
            raise NotFoundError(f"Patch Panel proposal '{proposal_id}' does not exist") from exc

    def approve(
        self,
        *,
        proposal_id: UUID,
        reviewer_id: str,
        runtime: CardRuntime,
        registry: PatchPanelRegistry,
        reason: str | None = None,
    ) -> PatchPanelProposal:
        proposal = self.get(proposal_id)
        if proposal.status != PatchPanelProposalStatus.IN_REVIEW:
            raise ConflictError("only in-review Patch Panel proposals can be approved")
        if not proposal.validation_report.valid:
            raise ConflictError("invalid Patch Panel proposals cannot be approved")

        runtime.register_patch_panel(proposal.candidate_definition)
        published_metadata = proposal.registry_metadata.model_copy(
            update={"status": PatchPanelRegistryStatus.PUBLISHED}
        )
        entry = registry.register(
            PatchPanelRegistryEntry.from_patch_panel(
                proposal.candidate_definition,
                published_metadata,
                metadata={"proposal_id": str(proposal.id)},
            )
        )
        promoted = proposal.model_copy(
            update={
                "status": PatchPanelProposalStatus.PROMOTED,
                "promoted_registry_entry_id": entry.id,
                "updated_at": datetime.now(UTC),
                "review_events": [
                    *proposal.review_events,
                    PatchPanelProposalReviewEvent(
                        actor_id=reviewer_id,
                        action="approved",
                        reason=reason,
                        metadata={"registry_entry_id": str(entry.id)},
                    ),
                ],
            }
        )
        self.proposals[proposal.id] = promoted
        return promoted

    def reject(
        self,
        *,
        proposal_id: UUID,
        reviewer_id: str,
        reason: str,
    ) -> PatchPanelProposal:
        proposal = self.get(proposal_id)
        if proposal.status != PatchPanelProposalStatus.IN_REVIEW:
            raise ConflictError("only in-review Patch Panel proposals can be rejected")
        rejected = proposal.model_copy(
            update={
                "status": PatchPanelProposalStatus.REJECTED,
                "updated_at": datetime.now(UTC),
                "review_events": [
                    *proposal.review_events,
                    PatchPanelProposalReviewEvent(
                        actor_id=reviewer_id,
                        action="rejected",
                        reason=reason,
                    ),
                ],
            }
        )
        self.proposals[proposal.id] = rejected
        return rejected


def _validate_candidate(candidate_definition: PatchPanel) -> PatchPanelValidationReport:
    try:
        PatchPanelValidator().validate(candidate_definition)
    except PatchPanelValidationError as exc:
        raise InvalidOperationError(f"Patch Panel proposal validation failed: {exc}") from exc
    return PatchPanelValidationReport(valid=True)
