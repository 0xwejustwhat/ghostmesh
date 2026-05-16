from __future__ import annotations

from ghostmesh.domain import AcceptanceContract, ArtifactReference
from ghostmesh.runtime.errors import InvalidOperationError


def validate_artifact_references(
    artifact_refs: list[ArtifactReference],
    acceptance_contract: AcceptanceContract | None,
) -> None:
    if acceptance_contract is None:
        return

    for rule in acceptance_contract.rules:
        rule_type = rule.get("type")
        if rule_type == "artifact_reference_structure":
            _validate_structure(artifact_refs)
        elif rule_type == "required_artifacts":
            _validate_required_artifacts(artifact_refs, rule)


def _validate_structure(artifact_refs: list[ArtifactReference]) -> None:
    for artifact_ref in artifact_refs:
        if not artifact_ref.storage_ref:
            raise InvalidOperationError("artifact reference is missing storage_ref")
        if not artifact_ref.content_hash.startswith("sha256:"):
            raise InvalidOperationError(
                f"artifact '{artifact_ref.id}' content_hash must use sha256"
            )
        if artifact_ref.size_bytes < 0:
            raise InvalidOperationError(f"artifact '{artifact_ref.id}' has invalid size")


def _validate_required_artifacts(
    artifact_refs: list[ArtifactReference],
    rule: dict[str, object],
) -> None:
    min_count = int(rule.get("min_count", 1))
    if len(artifact_refs) < min_count:
        raise InvalidOperationError(
            f"acceptance contract requires at least {min_count} artifact reference(s)"
        )

    required_roles = {str(role) for role in rule.get("roles", [])}
    if not required_roles:
        return

    present_roles = {str(ref.metadata.get("role")) for ref in artifact_refs}
    missing = required_roles - present_roles
    if missing:
        formatted = ", ".join(sorted(missing))
        raise InvalidOperationError(f"missing required artifact role(s): {formatted}")
