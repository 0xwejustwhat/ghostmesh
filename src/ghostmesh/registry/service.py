from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ghostmesh.domain import (
    PatchPanelRegistryEntry,
    PatchPanelRegistryMetadata,
    PatchPanelRegistryStatus,
    PermissionName,
)
from ghostmesh.persistence.tables import patch_panel_registry_entries
from ghostmesh.runtime.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class PatchPanelRegistrySearch:
    tag: str | None = None
    input_type: str | None = None
    output_type: str | None = None
    required_tool: str | None = None
    risk_level: str | None = None
    owner_participant_id: str | None = None
    include_archived: bool = False
    include_superseded: bool = False


class PatchPanelRegistry(Protocol):
    def register(self, entry: PatchPanelRegistryEntry) -> PatchPanelRegistryEntry: ...

    def get(self, entry_id: UUID) -> PatchPanelRegistryEntry: ...

    def search(self, filters: PatchPanelRegistrySearch) -> list[PatchPanelRegistryEntry]: ...

    def update_metadata(
        self, entry_id: UUID, metadata: PatchPanelRegistryMetadata
    ) -> PatchPanelRegistryEntry: ...

    def archive(self, entry_id: UUID) -> PatchPanelRegistryEntry: ...

    def supersede(
        self, entry_id: UUID, superseded_by_entry_id: UUID
    ) -> PatchPanelRegistryEntry: ...


class InMemoryPatchPanelRegistry:
    def __init__(self, entries: list[PatchPanelRegistryEntry] | None = None) -> None:
        self.entries = {entry.id: entry for entry in entries or []}

    def register(self, entry: PatchPanelRegistryEntry) -> PatchPanelRegistryEntry:
        self.entries[entry.id] = entry
        return entry

    def get(self, entry_id: UUID) -> PatchPanelRegistryEntry:
        try:
            return self.entries[entry_id]
        except KeyError as exc:
            raise NotFoundError(f"Patch Panel registry entry '{entry_id}' does not exist") from exc

    def search(self, filters: PatchPanelRegistrySearch) -> list[PatchPanelRegistryEntry]:
        return [entry for entry in self.entries.values() if _entry_matches(entry, filters)]

    def update_metadata(
        self, entry_id: UUID, metadata: PatchPanelRegistryMetadata
    ) -> PatchPanelRegistryEntry:
        entry = self.get(entry_id)
        if entry.status != PatchPanelRegistryStatus.DRAFT:
            raise ConflictError("only draft registry entries can be edited")
        updated = _entry_with_metadata(entry, metadata)
        self.entries[entry.id] = updated
        return updated

    def archive(self, entry_id: UUID) -> PatchPanelRegistryEntry:
        entry = self.get(entry_id).model_copy(
            update={
                "status": PatchPanelRegistryStatus.ARCHIVED,
                "archived_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        )
        self.entries[entry.id] = entry
        return entry

    def supersede(self, entry_id: UUID, superseded_by_entry_id: UUID) -> PatchPanelRegistryEntry:
        entry = self.get(entry_id).model_copy(
            update={
                "status": PatchPanelRegistryStatus.SUPERSEDED,
                "supersedes_entry_id": superseded_by_entry_id,
                "updated_at": datetime.now(UTC),
            }
        )
        self.entries[entry.id] = entry
        return entry


class PostgresPatchPanelRegistry:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def register(self, entry: PatchPanelRegistryEntry) -> PatchPanelRegistryEntry:
        with Session(self.engine) as session, session.begin():
            session.execute(patch_panel_registry_entries.insert().values(**_entry_values(entry)))
        return entry

    def get(self, entry_id: UUID) -> PatchPanelRegistryEntry:
        with Session(self.engine) as session:
            row = session.execute(
                select(patch_panel_registry_entries).where(
                    patch_panel_registry_entries.c.id == entry_id
                )
            ).first()
        if row is None:
            raise NotFoundError(f"Patch Panel registry entry '{entry_id}' does not exist")
        return _entry_from_row(row._mapping)

    def search(self, filters: PatchPanelRegistrySearch) -> list[PatchPanelRegistryEntry]:
        with Session(self.engine) as session:
            rows = session.execute(select(patch_panel_registry_entries)).all()
        entries = [_entry_from_row(row._mapping) for row in rows]
        return [entry for entry in entries if _entry_matches(entry, filters)]

    def update_metadata(
        self, entry_id: UUID, metadata: PatchPanelRegistryMetadata
    ) -> PatchPanelRegistryEntry:
        entry = self.get(entry_id)
        if entry.status != PatchPanelRegistryStatus.DRAFT:
            raise ConflictError("only draft registry entries can be edited")
        updated = _entry_with_metadata(entry, metadata)
        with Session(self.engine) as session, session.begin():
            session.execute(
                patch_panel_registry_entries.update()
                .where(patch_panel_registry_entries.c.id == entry_id)
                .values(**_entry_values(updated))
            )
        return updated

    def archive(self, entry_id: UUID) -> PatchPanelRegistryEntry:
        archived_at = datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                patch_panel_registry_entries.update()
                .where(patch_panel_registry_entries.c.id == entry_id)
                .values(
                    status=PatchPanelRegistryStatus.ARCHIVED.value,
                    archived_at=archived_at,
                    updated_at=archived_at,
                )
            )
            if result.rowcount == 0:
                raise NotFoundError(f"Patch Panel registry entry '{entry_id}' does not exist")
        return self.get(entry_id)

    def supersede(self, entry_id: UUID, superseded_by_entry_id: UUID) -> PatchPanelRegistryEntry:
        updated_at = datetime.now(UTC)
        with Session(self.engine) as session, session.begin():
            result = session.execute(
                patch_panel_registry_entries.update()
                .where(patch_panel_registry_entries.c.id == entry_id)
                .values(
                    status=PatchPanelRegistryStatus.SUPERSEDED.value,
                    supersedes_entry_id=superseded_by_entry_id,
                    updated_at=updated_at,
                )
            )
            if result.rowcount == 0:
                raise NotFoundError(f"Patch Panel registry entry '{entry_id}' does not exist")
        return self.get(entry_id)


def _entry_matches(entry: PatchPanelRegistryEntry, filters: PatchPanelRegistrySearch) -> bool:
    if not filters.include_archived and entry.status == PatchPanelRegistryStatus.ARCHIVED:
        return False
    if not filters.include_superseded and entry.status == PatchPanelRegistryStatus.SUPERSEDED:
        return False
    if filters.tag and filters.tag not in entry.tags:
        return False
    if filters.input_type and filters.input_type not in entry.input_types:
        return False
    if filters.output_type and filters.output_type not in entry.output_types:
        return False
    if filters.required_tool and filters.required_tool not in entry.required_tools:
        return False
    if filters.risk_level and filters.risk_level != entry.risk_level:
        return False
    if filters.owner_participant_id and filters.owner_participant_id != entry.owner_participant_id:
        return False
    return True


def _entry_values(entry: PatchPanelRegistryEntry) -> dict[str, object]:
    return {
        "id": entry.id,
        "patch_panel_id": entry.patch_panel_id,
        "version": entry.version,
        "name": entry.name,
        "description": entry.description,
        "tags": entry.tags,
        "input_types": entry.input_types,
        "output_types": entry.output_types,
        "required_tools": entry.required_tools,
        "required_permissions": [permission.value for permission in entry.required_permissions],
        "risk_level": entry.risk_level,
        "estimated_cost": entry.estimated_cost,
        "estimated_latency": entry.estimated_latency,
        "owner_participant_id": entry.owner_participant_id,
        "status": entry.status.value,
        "supersedes_entry_id": entry.supersedes_entry_id,
        "registry_metadata": entry.metadata,
        "created_at": entry.created_at,
        "updated_at": entry.updated_at,
        "archived_at": entry.archived_at,
    }


def _entry_with_metadata(
    entry: PatchPanelRegistryEntry,
    metadata: PatchPanelRegistryMetadata,
) -> PatchPanelRegistryEntry:
    return entry.model_copy(
        update={
            "name": metadata.name,
            "description": metadata.description,
            "tags": metadata.tags,
            "input_types": metadata.input_types,
            "output_types": metadata.output_types,
            "required_tools": metadata.required_tools,
            "required_permissions": metadata.required_permissions,
            "risk_level": metadata.risk_level,
            "estimated_cost": metadata.estimated_cost,
            "estimated_latency": metadata.estimated_latency,
            "owner_participant_id": metadata.owner_participant_id,
            "status": metadata.status,
            "updated_at": datetime.now(UTC),
        }
    )


def _entry_from_row(row: object) -> PatchPanelRegistryEntry:
    data = dict(row)
    return PatchPanelRegistryEntry(
        id=data["id"],
        patch_panel_id=data["patch_panel_id"],
        version=data["version"],
        name=data["name"],
        description=data["description"],
        tags=data["tags"],
        input_types=data["input_types"],
        output_types=data["output_types"],
        required_tools=data["required_tools"],
        required_permissions=[
            PermissionName(permission) for permission in data["required_permissions"]
        ],
        risk_level=data["risk_level"],
        estimated_cost=data["estimated_cost"],
        estimated_latency=data["estimated_latency"],
        owner_participant_id=data["owner_participant_id"],
        status=PatchPanelRegistryStatus(data["status"]),
        supersedes_entry_id=data["supersedes_entry_id"],
        metadata=data["registry_metadata"],
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        archived_at=data["archived_at"],
    )
