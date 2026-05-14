from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from ghostmesh.domain import Card, MutationStatus, PatchPanel, ProposedMutation, ShadowCardLink
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError, NotFoundError
from ghostmesh.runtime.service import CardRuntime


@dataclass(frozen=True)
class ShadowRun:
    production_card: Card
    shadow_card: Card
    shadow_metadata: dict[str, Any]


@dataclass(frozen=True)
class ShadowPolicy:
    sample_rate: float = 1.0
    max_parallel: int = 1


class ShadowService:
    """Executable shadow and mutation-safety service for Phase 6."""

    def __init__(self, runtime: CardRuntime) -> None:
        self.runtime = runtime
        self.links: dict[UUID, ShadowCardLink] = {}
        self.mutations: dict[UUID, ProposedMutation] = {}

    def create_shadow_card(
        self,
        *,
        production_card: Card,
        candidate_id: str,
        policy: ShadowPolicy | None = None,
        idempotency_key: str | None = None,
    ) -> ShadowRun:
        policy = policy or ShadowPolicy()
        if policy.sample_rate <= 0:
            raise InvalidOperationError("shadow sampling skipped this card")

        active_links = [
            link
            for link in self.links.values()
            if link.production_card_id == production_card.id and link.status == "active"
        ]
        if len(active_links) >= policy.max_parallel:
            raise ConflictError(
                f"production card '{production_card.id}' already has maximum parallel shadows"
            )

        patch_panel_id = production_card.workflow_version.split(":", maxsplit=1)[0]
        shadow_card = self.runtime.create_card(
            patch_panel_id=patch_panel_id,
            payload=production_card.payload,
            metadata={
                **production_card.metadata,
                "shadow": True,
                "production_card_id": str(production_card.id),
                "candidate_id": candidate_id,
            },
            idempotency_key=idempotency_key,
        )
        link = ShadowCardLink(
            production_card_id=production_card.id,
            shadow_card_id=shadow_card.id,
            candidate_id=candidate_id,
        )
        self.links[link.id] = link
        self.runtime.record_event(
            card_id=production_card.id,
            event_type="shadow_created",
            actor_id=candidate_id,
            payload={
                "shadow_card_id": str(shadow_card.id),
                "shadow_link_id": str(link.id),
                "candidate_id": candidate_id,
            },
        )
        return ShadowRun(
            production_card=production_card,
            shadow_card=shadow_card,
            shadow_metadata={
                "production_card_id": str(production_card.id),
                "shadow_card_id": str(shadow_card.id),
                "shadow_link_id": str(link.id),
                "candidate_id": candidate_id,
            },
        )

    def complete_shadow(
        self,
        *,
        link_id: UUID,
        metrics: dict[str, Any],
    ) -> ShadowCardLink:
        link = self._link(link_id)
        completed = link.model_copy(update={"status": "completed", "metrics": metrics})
        self.links[link_id] = completed
        self.runtime.record_event(
            card_id=completed.production_card_id,
            event_type="shadow_completed",
            actor_id=completed.candidate_id,
            payload={"shadow_link_id": str(link_id), "metrics": metrics},
        )
        return completed

    def propose_mutation(
        self,
        *,
        mutation_type: str,
        proposed_by: str,
        payload: dict[str, Any],
    ) -> ProposedMutation:
        mutation = ProposedMutation(
            mutation_type=mutation_type,
            proposed_by=proposed_by,
            payload=payload,
            status=MutationStatus.SHADOWING,
        )
        self.mutations[mutation.id] = mutation
        return mutation

    def validate_mutation(
        self,
        *,
        mutation_id: UUID,
        accepted: bool,
        validator_id: str,
        reason: str | None = None,
    ) -> ProposedMutation:
        mutation = self._mutation(mutation_id)
        status = MutationStatus.VALIDATED if accepted else MutationStatus.REJECTED
        validated = mutation.model_copy(
            update={
                "status": status,
                "validated_at": datetime.now(UTC),
                "payload": {
                    **mutation.payload,
                    "validation": {"validator_id": validator_id, "reason": reason},
                },
            }
        )
        self.mutations[mutation_id] = validated
        return validated

    def promote_mutation(
        self,
        *,
        mutation_id: UUID,
        patch_panel: PatchPanel,
    ) -> ProposedMutation:
        mutation = self._mutation(mutation_id)
        if mutation.status != MutationStatus.VALIDATED:
            raise ConflictError("only validated mutations can be promoted")
        self.runtime.register_patch_panel(patch_panel)
        promoted = mutation.model_copy(
            update={"status": MutationStatus.PROMOTED, "promoted_at": datetime.now(UTC)}
        )
        self.mutations[mutation_id] = promoted
        return promoted

    def _link(self, link_id: UUID) -> ShadowCardLink:
        try:
            return self.links[link_id]
        except KeyError as exc:
            raise NotFoundError(f"shadow link '{link_id}' does not exist") from exc

    def _mutation(self, mutation_id: UUID) -> ProposedMutation:
        try:
            return self.mutations[mutation_id]
        except KeyError as exc:
            raise NotFoundError(f"mutation '{mutation_id}' does not exist") from exc


ShadowHarness = ShadowService
