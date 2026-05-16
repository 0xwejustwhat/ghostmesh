from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from ghostmesh.domain import Card, CardEvent, NodeType, PatchPanel
from ghostmesh.runtime import CardRuntime
from ghostmesh.runtime.errors import NotFoundError


class ObservabilityService:
    """Read-only operator views derived from cards, leases, and evidence."""

    def __init__(self, *, runtime: CardRuntime) -> None:
        self.runtime = runtime

    def topology(self, patch_panel_id: str) -> dict[str, Any]:
        patch_panel = self._patch_panel(patch_panel_id)
        return {
            "patch_panel_id": patch_panel.id,
            "version": patch_panel.version,
            "nodes": [
                {
                    "id": node.id,
                    "type": node.type,
                    "validator_kind": node.validator_kind,
                    "input_pipes": node.input_pipes,
                    "output_pipes": node.output_pipes,
                }
                for node in patch_panel.nodes
            ],
            "edges": [
                {
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "on": edge.on,
                    "condition": edge.condition,
                }
                for edge in patch_panel.edges
            ],
            "buckets": [bucket.model_dump(mode="json") for bucket in patch_panel.buckets],
            "mermaid": _mermaid(patch_panel),
        }

    def cards_by_bucket(self) -> dict[str, list[Card]]:
        grouped: dict[str, list[Card]] = defaultdict(list)
        for card in self.runtime.list_cards():
            grouped[card.current_bucket].append(card)
        return dict(grouped)

    def bucket_load(self) -> dict[str, int]:
        return {
            bucket: len(cards)
            for bucket, cards in sorted(self.cards_by_bucket().items(), key=lambda item: item[0])
        }

    def active_leases(self) -> list[dict[str, Any]]:
        now = datetime.now(UTC)
        active: list[dict[str, Any]] = []
        for lease in self.runtime.list_leases():
            expires_at = _aware(lease.expires_at)
            if lease.released_at is None and expires_at > now:
                active.append(
                    {
                        "lease": lease,
                        "age_seconds": int((now - _aware(lease.claimed_at)).total_seconds()),
                        "expires_in_seconds": int((expires_at - now).total_seconds()),
                    }
                )
        return active

    def worker_activity(self) -> dict[str, dict[str, int]]:
        activity: dict[str, Counter[str]] = defaultdict(Counter)
        for event in self._all_events():
            if event.event_type in {
                "card_claimed",
                "artifact_submitted",
                "lease_renewed",
                "lease_released",
                "lease_expired",
            }:
                worker_id = event.actor_id or "unknown"
                activity[worker_id][event.event_type] += 1
        return {worker_id: dict(counts) for worker_id, counts in activity.items()}

    def validator_decisions(self) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        for event in self._all_events():
            if event.event_type == "card_validated":
                decisions.append(
                    {
                        "card_id": event.card_id,
                        "validator_id": event.actor_id,
                        "accepted": event.payload.get("accepted"),
                        "reason": event.payload.get("reason"),
                        "occurred_at": event.occurred_at,
                    }
                )
        return decisions

    def workflow_versions(self) -> list[dict[str, Any]]:
        return [
            {
                "id": f"{patch_panel.id}:{patch_panel.version}",
                "patch_panel_id": patch_panel.id,
                "version": patch_panel.version,
                "active": True,
            }
            for patch_panel in self.runtime.list_patch_panels()
        ]

    def failed_movements(self) -> list[CardEvent]:
        return [
            event
            for event in self._all_events()
            if event.event_type in {"card_move_failed", "failed_dropoff", "sink_failed"}
        ]

    def metrics(self) -> dict[str, Any]:
        events = self._all_events()
        event_counts = Counter(event.event_type for event in events)
        validator_events = [
            event for event in events if event.event_type == "card_validated"
        ]
        accepted = sum(1 for event in validator_events if event.payload.get("accepted") is True)
        active_leases = self.active_leases()
        return {
            "card_count": len(self.runtime.list_cards()),
            "bucket_load": self.bucket_load(),
            "active_lease_count": len(active_leases),
            "worker_activity": self.worker_activity(),
            "event_counts": dict(event_counts),
            "acceptance_rate": accepted / len(validator_events) if validator_events else None,
            "retry_rate": _retry_rate(events),
            "failed_movement_count": len(self.failed_movements()),
            "oldest_active_lease_age_seconds": max(
                (lease["age_seconds"] for lease in active_leases),
                default=0,
            ),
        }

    def dashboard(self, patch_panel_id: str) -> dict[str, Any]:
        return {
            "topology": self.topology(patch_panel_id),
            "bucket_load": self.bucket_load(),
            "active_leases": self.active_leases(),
            "worker_activity": self.worker_activity(),
            "validator_decisions": self.validator_decisions(),
            "failed_movements": self.failed_movements(),
            "metrics": self.metrics(),
        }

    def _patch_panel(self, patch_panel_id: str) -> PatchPanel:
        for patch_panel in self.runtime.list_patch_panels():
            if patch_panel.id == patch_panel_id:
                return patch_panel
        raise NotFoundError(f"Patch Panel '{patch_panel_id}' is not registered")

    def _all_events(self) -> list[CardEvent]:
        events: list[CardEvent] = []
        for card in self.runtime.list_cards():
            events.extend(self.runtime.card_history(card.id))
        return sorted(events, key=lambda event: (event.occurred_at, str(event.id)))


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _retry_rate(events: list[CardEvent]) -> float | None:
    retry_events = [
        event
        for event in events
        if event.event_type in {"lease_expired", "card_move_failed", "failed_dropoff"}
    ]
    claim_events = [event for event in events if event.event_type == "card_claimed"]
    if not claim_events:
        return None
    return len(retry_events) / len(claim_events)


def _mermaid(patch_panel: PatchPanel) -> str:
    lines = ["flowchart LR"]
    for node in patch_panel.nodes:
        shape = _node_shape(node.id, node.type)
        lines.append(f"  {node.id}{shape}")
    for edge in patch_panel.edges:
        lines.append(f"  {edge.from_node} -- {edge.on} --> {edge.to_node}")
    return "\n".join(lines)


def _node_shape(node_id: str, node_type: NodeType) -> str:
    label = f"{node_id}\\n{node_type.value}"
    if node_type == NodeType.SOURCE:
        return f'(["{label}"])'
    if node_type == NodeType.SINK:
        return f'(["{label}"])'
    return f'["{label}"]'
