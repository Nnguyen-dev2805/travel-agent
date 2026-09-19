"""Typed contracts for exact, governed semantic Memory reads."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol, Sequence

from backend.memory.lifecycle import SourceValidity
from backend.memory.write_pipeline.models import Authority, MemoryScope, NormalizedSemanticValue, RetentionMode, SensitivityBand, VersionStatus
from backend.memory.write_pipeline.registry import get_key_definition

MAX_SELECTED = 8

class AbstentionReason(str, Enum):
    NO_REQUESTED_KEYS = "no_requested_keys"
    NO_ELIGIBLE_MEMORY = "no_eligible_memory"

@dataclass(frozen=True)
class MemoryReadRequest:
    owner_user_id: str
    requested_keys: tuple[str, ...] = ()
    conversation_id: str | None = None
    max_selected: int = MAX_SELECTED

    def __post_init__(self) -> None:
        if (not isinstance(self.max_selected, int) or isinstance(self.max_selected, bool)
                or not self.owner_user_id.strip() or not 1 <= self.max_selected <= MAX_SELECTED):
            raise ValueError("owner_user_id and max_selected must be valid.")
        keys_tuple = tuple(self.requested_keys)
        object.__setattr__(self, "requested_keys", keys_tuple)
        if len(set(keys_tuple)) != len(keys_tuple):
            raise ValueError("requested_keys must not repeat.")
        for key in keys_tuple:
            get_key_definition(key)


@dataclass(frozen=True)
class StoredMemoryRow:
    version_id: str
    canonical_key: str
    normalized_value: NormalizedSemanticValue
    owner_user_id: str
    scope: MemoryScope
    scope_id: str
    authority: Authority
    valid_from: datetime
    retention_mode: RetentionMode
    stamped_generation: int
    current_generation: int
    status: VersionStatus
    sensitivity: SensitivityBand
    source_validity: SourceValidity
    expires_at: datetime | None = None
    unresolved_conflict: bool = False


@dataclass(frozen=True)
class SelectedMemory:
    version_id: str
    canonical_key: str
    normalized_value: NormalizedSemanticValue
    scope: MemoryScope
    scope_id: str
    authority: Authority
    valid_from: datetime

@dataclass(frozen=True)
class MemorySelection:
    selected: tuple[SelectedMemory, ...]
    abstention_reason: AbstentionReason | None = None

class MemoryStore(Protocol):
    def list_storage_scoped(self, request: MemoryReadRequest) -> Sequence[StoredMemoryRow]: ...
