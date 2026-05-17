from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from ghostmesh.auth import AuthorizationRepository
from ghostmesh.bootstrap import ensure_builtin_role_assignment
from ghostmesh.domain import (
    ArtifactReference,
    Card,
    CardEvent,
    NodeDefinition,
    NodeType,
    Participant,
    PatchPanel,
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    RoleName,
    Scope,
)
from ghostmesh.patchpanel import PatchPanelValidator
from ghostmesh.patchpanel.errors import PatchPanelValidationError
from ghostmesh.registry import PatchPanelRegistry, PatchPanelRegistrySearch
from ghostmesh.runtime import CardRuntime
from ghostmesh.runtime.errors import ConflictError, InvalidOperationError, NotFoundError


class WorkerExecutionInput(BaseModel):
    input_pipe: str
    output_pipe: str
    worker_id: str
    artifact_refs: list[ArtifactReference]
    lease_seconds: int = 300
    idempotency_key: str | None = None


class ValidatorExecutionInput(BaseModel):
    card_id: UUID
    validator_id: str
    selected_exit: str | None = None
    accepted: bool | None = None
    score: int | None = Field(default=None, ge=0, le=10)
    reason: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


class OnboardingRoleAssignmentPayload(BaseModel):
    role_name: RoleName
    scope: Scope
    assigned_by: str | None = None


class ParticipantOnboardingPayload(BaseModel):
    participant: Participant
    role_assignments: list[OnboardingRoleAssignmentPayload] = Field(min_length=1)


@dataclass(frozen=True)
class SinkResult:
    event: CardEvent
    external_reference: str | None


class NodeExecutor:
    """MVP node execution layer composed from runtime primitives."""

    def __init__(
        self,
        *,
        patch_panel: PatchPanel,
        runtime: CardRuntime,
        registry: PatchPanelRegistry | None = None,
        authorization_repository: AuthorizationRepository | None = None,
    ) -> None:
        self.patch_panel = patch_panel
        self.runtime = runtime
        self.registry = registry
        self.authorization_repository = authorization_repository

    def execute_source(
        self,
        *,
        source_id: str,
        payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> Card:
        node = self._node(source_id, NodeType.SOURCE)
        card = self.runtime.create_card(
            patch_panel_id=self.patch_panel.id,
            payload=payload,
            metadata=metadata or {},
            idempotency_key=idempotency_key,
        )
        self.runtime.record_event(
            card_id=card.id,
            event_type="source_executed",
            actor_id=node.id,
            payload={"source_id": node.id},
            idempotency_key=f"{idempotency_key}:source" if idempotency_key else None,
        )
        return card

    def execute_worker(self, request: WorkerExecutionInput) -> list[ArtifactReference]:
        node_id = self._node_for_pipe(request.input_pipe, NodeType.WORKER).id
        lease = self.runtime.claim_card(
            input_pipe=request.input_pipe,
            worker_id=request.worker_id,
            lease_seconds=request.lease_seconds,
            idempotency_key=f"{request.idempotency_key}:claim" if request.idempotency_key else None,
        )
        artifact_refs = self.runtime.submit_artifact(
            lease_id=lease.id,
            output_pipe=request.output_pipe,
            artifact_refs=request.artifact_refs,
            idempotency_key=(
                f"{request.idempotency_key}:submit" if request.idempotency_key else None
            ),
        )
        if not artifact_refs:
            raise InvalidOperationError("worker execution produced no artifact references")
        event = self.runtime.card_history(lease.card_id)[-1]
        event_node_id = self.patch_panel.pipe_bindings[request.output_pipe].node
        if event_node_id != node_id:
            raise InvalidOperationError(
                f"worker pipe '{request.input_pipe}' resolved to '{node_id}' but output pipe "
                f"was bound to '{event_node_id}'"
            )
        if event.event_type != "artifact_submitted":
            raise InvalidOperationError("worker execution did not submit artifacts")
        return artifact_refs

    def execute_validator(self, request: ValidatorExecutionInput) -> CardEvent:
        node = self._node(request.validator_id, NodeType.VALIDATOR)
        if node.config.get("validation_handler") == "patch_panel_topology":
            request = self._topology_validation_request(node, request)
        if node.config.get("validation_handler") == "participant_onboarding_compliance":
            request = self._participant_onboarding_request(node, request)
        selected_exit = request.selected_exit
        if selected_exit is None and self._requires_selected_exit(node):
            raise InvalidOperationError(
                f"routing validator '{node.id}' requires selected_exit"
            )
        if selected_exit is not None:
            self._ensure_validator_exit(node, selected_exit)
        accepted = self._validator_accepted(node, request)
        return self.runtime.validate_card(
            card_id=request.card_id,
            validator_id=node.id,
            accepted=accepted,
            reason=request.reason,
            output_pipe=selected_exit,
            payload=request.payload,
            idempotency_key=request.idempotency_key,
        )

    def execute_sink(
        self,
        *,
        card_id: UUID,
        sink_id: str,
        external_reference: str | None = None,
        idempotency_key: str | None = None,
    ) -> SinkResult:
        node = self._node(sink_id, NodeType.SINK)
        card = self.runtime.get_card(card_id)
        if card.metadata.get("shadow") and not node.config.get("allow_shadow_egress", False):
            raise InvalidOperationError("shadow cards cannot execute production sinks")
        self._ensure_card_at_sink(node, card)
        external_reference = self._execute_configured_sink(
            node,
            card,
            external_reference,
        )
        event = self.runtime.record_event(
            card_id=card_id,
            event_type="sink_executed",
            actor_id=node.id,
            payload={
                "sink_id": node.id,
                "external_reference": external_reference,
                "registry_entry_id": (
                    external_reference
                    if _egress_contract_type(node) == "registry_publication"
                    else None
                ),
                "egress_contract": node.config.get("egress_contract"),
                "egress_idempotency": node.config.get("egress_idempotency"),
            },
            idempotency_key=idempotency_key,
        )
        return SinkResult(event=event, external_reference=external_reference)

    def _topology_validation_request(
        self,
        node: NodeDefinition,
        request: ValidatorExecutionInput,
    ) -> ValidatorExecutionInput:
        if request.accepted is not None or request.selected_exit is not None:
            return request

        card = self.runtime.get_card(request.card_id)
        valid_exit = _configured_exit(node, "valid_exit")
        invalid_exit = _configured_exit(node, "invalid_exit")
        try:
            candidate = PatchPanel.model_validate(card.payload.get("candidate_definition"))
            report = PatchPanelValidator().validate(candidate)
        except (PatchPanelValidationError, ValueError) as exc:
            payload = {
                **request.payload,
                "validation_handler": "patch_panel_topology",
                "candidate_patch_panel_id": _candidate_id(card.payload),
                "errors": _validation_errors(exc),
            }
            return request.model_copy(
                update={
                    "accepted": False,
                    "selected_exit": invalid_exit,
                    "reason": str(exc),
                    "payload": payload,
                }
            )

        payload = {
            **request.payload,
            "validation_handler": "patch_panel_topology",
            "candidate_patch_panel_id": candidate.id,
            "node_count": report.node_count,
            "edge_count": report.edge_count,
            "cycles": report.cycles,
        }
        return request.model_copy(
            update={
                "accepted": True,
                "selected_exit": valid_exit,
                "reason": request.reason or "Patch Panel topology validation passed",
                "payload": payload,
            }
        )

    def _ensure_card_at_sink(self, node: NodeDefinition, card: Card) -> None:
        input_buckets = {
            self.patch_panel.pipe_bindings[pipe].bucket
            for pipe in node.input_pipes
            if pipe in self.patch_panel.pipe_bindings
        }
        if input_buckets and card.current_bucket not in input_buckets:
            formatted = ", ".join(sorted(input_buckets))
            raise ConflictError(
                f"card '{card.id}' is in bucket '{card.current_bucket}', not sink input "
                f"bucket(s): {formatted}"
            )

    def _execute_configured_sink(
        self,
        node: NodeDefinition,
        card: Card,
        external_reference: str | None,
    ) -> str | None:
        contract = node.config.get("egress_contract")
        if node.id == "authority_provisioner_sink":
            return self._execute_authority_provisioning_sink(node, card, external_reference)
        if not isinstance(contract, dict) or contract.get("type") != "registry_publication":
            return external_reference
        if self.registry is None:
            raise InvalidOperationError("registry publication sink requires a registry")
        self._ensure_registry_publication_history(card)

        candidate = PatchPanel.model_validate(card.payload.get("candidate_definition"))
        metadata = PatchPanelRegistryMetadata.model_validate(card.payload.get("registry_metadata"))
        published_metadata = metadata.model_copy(
            update={"status": PatchPanelRegistryStatus.PUBLISHED}
        )
        self.runtime.register_patch_panel(candidate)
        existing = next(
            (
                entry
                for entry in self.registry.search(
                    PatchPanelRegistrySearch(include_archived=True, include_superseded=True)
                )
                if entry.patch_panel_id == candidate.id and entry.version == candidate.version
            ),
            None,
        )
        if existing is None:
            entry = self.registry.register(
                PatchPanelRegistryEntry.from_patch_panel(
                    candidate,
                    published_metadata,
                    metadata={
                        "proposal_card_id": str(card.id),
                        "published_by_sink": node.id,
                        "genesis_intent_id": card.payload.get("genesis_intent_id"),
                    },
                )
            )
        else:
            entry = existing
        return external_reference or str(entry.id)

    def _ensure_registry_publication_history(self, card: Card) -> None:
        history = self.runtime.card_history(card.id)
        topology_validated = any(
            event.event_type == "card_validated"
            and event.actor_id == "topological_validator"
            and event.payload.get("accepted") is True
            and event.payload.get("output_pipe") == "topology_valid"
            for event in history
        )
        governance_approved = any(
            event.event_type == "card_validated"
            and event.actor_id == "governance_reviewer"
            and event.payload.get("accepted") is True
            and event.payload.get("output_pipe") == "proposal_approved"
            for event in history
        )
        if not topology_validated or not governance_approved:
            raise ConflictError(
                "registry publication requires topology validation and governance approval history"
            )

    def _participant_onboarding_request(
        self,
        node: NodeDefinition,
        request: ValidatorExecutionInput,
    ) -> ValidatorExecutionInput:
        if request.accepted is not None or request.selected_exit is not None:
            return request

        card = self.runtime.get_card(request.card_id)
        valid_exit = _configured_exit(node, "valid_exit")
        invalid_exit = _configured_exit(node, "invalid_exit")
        try:
            payload = ParticipantOnboardingPayload.model_validate(card.payload)
        except ValueError as exc:
            return request.model_copy(
                update={
                    "accepted": False,
                    "selected_exit": invalid_exit,
                    "reason": str(exc),
                    "payload": {
                        **request.payload,
                        "validation_handler": "participant_onboarding_compliance",
                        "errors": [str(exc)],
                    },
                }
            )

        return request.model_copy(
            update={
                "accepted": True,
                "selected_exit": valid_exit,
                "reason": request.reason or "Participant onboarding payload is compliant",
                "payload": {
                    **request.payload,
                    "validation_handler": "participant_onboarding_compliance",
                    "participant_id": payload.participant.id,
                    "role_assignment_count": len(payload.role_assignments),
                },
            }
        )

    def _execute_authority_provisioning_sink(
        self,
        node: NodeDefinition,
        card: Card,
        external_reference: str | None,
    ) -> str | None:
        if self.authorization_repository is None:
            raise InvalidOperationError(
                "Authorization repository unavailable for system provisioning"
            )
        self._ensure_authority_provisioning_history(card)
        payload = ParticipantOnboardingPayload.model_validate(card.payload)
        self.authorization_repository.upsert_participant(payload.participant)
        for assignment in payload.role_assignments:
            ensure_builtin_role_assignment(
                self.authorization_repository,
                participant_id=payload.participant.id,
                role_name=assignment.role_name,
                scope=assignment.scope,
                assigned_by=assignment.assigned_by,
            )
        return external_reference or payload.participant.id

    def _ensure_authority_provisioning_history(self, card: Card) -> None:
        history = self.runtime.card_history(card.id)
        compliance_validated = any(
            event.event_type == "card_validated"
            and event.actor_id == "registration_compliance_validator"
            and event.payload.get("accepted") is True
            and event.payload.get("output_pipe") == "registration_compliant"
            for event in history
        )
        admin_approved = any(
            event.event_type == "card_validated"
            and event.actor_id == "registration_admin_reviewer"
            and event.payload.get("accepted") is True
            and event.payload.get("output_pipe") == "registration_approved"
            for event in history
        )
        if not compliance_validated or not admin_approved:
            raise ConflictError(
                "authority provisioning requires compliance validation and admin approval history"
            )

    def _node(self, node_id: str, expected_type: NodeType) -> NodeDefinition:
        for node in self.patch_panel.nodes:
            if node.id == node_id:
                if node.type != expected_type:
                    raise InvalidOperationError(
                        f"node '{node_id}' is '{node.type}', not '{expected_type}'"
                    )
                return node
        raise NotFoundError(f"node '{node_id}' does not exist")

    def _node_for_pipe(self, pipe: str, expected_type: NodeType) -> NodeDefinition:
        binding = self.patch_panel.pipe_bindings.get(pipe)
        if binding is None or binding.node is None:
            raise NotFoundError(f"pipe '{pipe}' is not bound to a node")
        return self._node(binding.node, expected_type)

    def _ensure_validator_exit(self, node: NodeDefinition, selected_exit: str) -> None:
        if selected_exit not in node.output_pipes:
            raise InvalidOperationError(
                f"exit pipe '{selected_exit}' is not declared by validator '{node.id}'"
            )
        binding = self.patch_panel.pipe_bindings.get(selected_exit)
        if binding is None:
            raise InvalidOperationError(
                f"selected exit pipe '{selected_exit}' is missing a Patch Panel binding"
            )
        if binding.node != node.id or binding.direction != "output":
            raise InvalidOperationError(
                f"selected exit pipe '{selected_exit}' is not an output binding for validator "
                f"'{node.id}'"
            )

    def _requires_selected_exit(self, node: NodeDefinition) -> bool:
        return node.validator_kind == "routing" or len(node.output_pipes) > 1

    def _validator_accepted(self, node: NodeDefinition, request: ValidatorExecutionInput) -> bool:
        if request.accepted is not None:
            return request.accepted
        if request.selected_exit is None:
            raise InvalidOperationError(
                f"validator '{node.id}' requires either accepted or selected_exit"
            )
        accept_exits = node.config.get("accept_exits")
        if isinstance(accept_exits, list):
            return request.selected_exit in accept_exits
        raise InvalidOperationError(
            f"routing validator '{node.id}' requires config.accept_exits when accepted "
            "is not provided"
        )


def _configured_exit(node: NodeDefinition, key: str) -> str:
    value = node.config.get(key)
    if not isinstance(value, str):
        raise InvalidOperationError(f"validator '{node.id}' requires config.{key}")
    return value


def _candidate_id(payload: dict[str, Any]) -> str | None:
    candidate = payload.get("candidate_definition")
    if isinstance(candidate, dict):
        value = candidate.get("id")
        return str(value) if value is not None else None
    return None


def _validation_errors(exc: Exception) -> list[str]:
    if isinstance(exc, PatchPanelValidationError):
        return exc.errors
    return [str(exc)]


def _egress_contract_type(node: NodeDefinition) -> str | None:
    contract = node.config.get("egress_contract")
    if isinstance(contract, dict):
        value = contract.get("type")
        return str(value) if value is not None else None
    return None
