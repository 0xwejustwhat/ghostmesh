from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ghostmesh.domain import Card
from ghostmesh.runtime.memory import InMemoryCardRuntime


@dataclass(frozen=True)
class ShadowRun:
    production_card: Card
    shadow_card: Card
    shadow_metadata: dict[str, Any]


class ShadowHarness:
    """Small test harness proving shadow cards are linked and isolated."""

    def __init__(self, runtime: InMemoryCardRuntime) -> None:
        self.runtime = runtime

    def create_shadow_card(
        self,
        *,
        production_card: Card,
        candidate_id: str,
        idempotency_key: str | None = None,
    ) -> ShadowRun:
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
        return ShadowRun(
            production_card=production_card,
            shadow_card=shadow_card,
            shadow_metadata={
                "production_card_id": str(production_card.id),
                "shadow_card_id": str(shadow_card.id),
                "candidate_id": candidate_id,
            },
        )

