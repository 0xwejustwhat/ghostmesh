from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from ghostmesh.domain import (
    Card,
    GenesisIntent,
    GenesisIntentConstraints,
    GenesisIntentStatus,
    PatchPanel,
    PatchPanelProposal,
    PatchPanelProposalType,
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
)
from ghostmesh.registry import PatchPanelProposalStore, PatchPanelRegistry, PatchPanelRegistrySearch
from ghostmesh.runtime.errors import ConflictError, NotFoundError
from ghostmesh.runtime.service import CardRuntime


class GenesisService:
    def __init__(
        self,
        *,
        runtime: CardRuntime,
        registry: PatchPanelRegistry,
        proposal_store: PatchPanelProposalStore,
    ) -> None:
        self.runtime = runtime
        self.registry = registry
        self.proposal_store = proposal_store
        self.intents: dict[UUID, GenesisIntent] = {}
        self.deduplication_index: dict[str, UUID] = {}

    def receive_intent(
        self,
        *,
        requested_by: str,
        deduplication_key: str,
        goal: str,
        input_type: str,
        desired_outputs: list[str],
        tags: list[str],
        constraints: GenesisIntentConstraints,
        launch_if_existing: bool,
        propose_if_missing: bool,
        metadata: dict[str, object] | None = None,
    ) -> GenesisIntent:
        if deduplication_key in self.deduplication_index:
            return self.get(self.deduplication_index[deduplication_key])

        intent = GenesisIntent(
            requested_by=requested_by,
            deduplication_key=deduplication_key,
            goal=goal,
            input_type=input_type,
            desired_outputs=desired_outputs,
            tags=tags,
            constraints=constraints,
            launch_if_existing=launch_if_existing,
            propose_if_missing=propose_if_missing,
            metadata=dict(metadata or {}),
        )
        candidates = self.search_candidates(intent)
        intent = intent.model_copy(
            update={"candidate_registry_entry_ids": [candidate.id for candidate in candidates]}
        )
        if not candidates and propose_if_missing:
            intent = intent.model_copy(
                update={
                    "status": GenesisIntentStatus.DESIGN_REQUIRED,
                    "updated_at": datetime.now(UTC),
                }
            )
        self.intents[intent.id] = intent
        self.deduplication_index[deduplication_key] = intent.id
        return intent

    def get(self, intent_id: UUID) -> GenesisIntent:
        try:
            return self.intents[intent_id]
        except KeyError as exc:
            raise NotFoundError(f"genesis intent '{intent_id}' does not exist") from exc

    def search_candidates(self, intent: GenesisIntent) -> list[PatchPanelRegistryEntry]:
        candidates: list[PatchPanelRegistryEntry] = []
        seen: set[UUID] = set()
        filters = [
            PatchPanelRegistrySearch(input_type=intent.input_type),
            *[PatchPanelRegistrySearch(output_type=output) for output in intent.desired_outputs],
            *[PatchPanelRegistrySearch(tag=tag) for tag in intent.tags],
        ]
        if intent.constraints.risk_level:
            filters.append(PatchPanelRegistrySearch(risk_level=intent.constraints.risk_level))

        for registry_filter in filters:
            for candidate in self.registry.search(registry_filter):
                if candidate.id not in seen:
                    seen.add(candidate.id)
                    candidates.append(candidate)
        return candidates

    def launch(self, *, intent_id: UUID, registry_entry_id: UUID | None = None) -> Card:
        intent = self.get(intent_id)
        candidate_ids = intent.candidate_registry_entry_ids
        selected_id = registry_entry_id or (candidate_ids[0] if candidate_ids else None)
        if selected_id is None:
            raise ConflictError("genesis intent has no registry candidate to launch")

        entry = self.registry.get(selected_id)
        card = self.runtime.create_card(
            patch_panel_id=entry.patch_panel_id,
            payload={
                "goal": intent.goal,
                "input_type": intent.input_type,
                "desired_outputs": intent.desired_outputs,
                "tags": intent.tags,
                "constraints": intent.constraints.model_dump(mode="json"),
            },
            metadata={
                "genesis_intent_id": str(intent.id),
                "registry_entry_id": str(entry.id),
                "requested_by": intent.requested_by,
            },
            idempotency_key=f"genesis:launch:{intent.deduplication_key}:{entry.id}",
        )
        updated = intent.model_copy(
            update={
                "status": GenesisIntentStatus.LAUNCHED,
                "selected_registry_entry_id": entry.id,
                "launched_card_id": card.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.intents[intent.id] = updated
        return card

    def propose(
        self,
        *,
        intent_id: UUID,
        proposed_by: str,
        candidate_definition: PatchPanel,
        registry_metadata: PatchPanelRegistryMetadata,
    ) -> PatchPanelProposal:
        intent = self.get(intent_id)
        proposal = self.proposal_store.create(
            proposal_type=PatchPanelProposalType.CREATE,
            proposed_by=proposed_by,
            candidate_definition=candidate_definition,
            registry_metadata=registry_metadata,
        )
        updated = intent.model_copy(
            update={
                "status": GenesisIntentStatus.PROPOSED,
                "proposal_id": proposal.id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.intents[intent.id] = updated
        return proposal
