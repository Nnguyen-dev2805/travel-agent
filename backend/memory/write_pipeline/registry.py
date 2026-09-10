"""Versioned semantic registry: the first canonical key.

Defines `travel.preference.hotel_atmosphere` with its normalized values,
single cardinality, allowed scopes, ordinary-personal floor, and governed
bilingual synonyms. This module depends on the Python standard library
and the sibling contract module only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.memory.write_pipeline.models import (
    SENSITIVITY_RANK,
    Cardinality,
    MemoryCandidate,
    MemoryScope,
    SensitivityBand,
)

SEMANTIC_REGISTRY_VERSION = "semantic-registry-v1"
HOTEL_ATMOSPHERE_KEY = "travel.preference.hotel_atmosphere"


class HotelAtmosphere(str, Enum):
    """Normalized hotel-atmosphere values; identity compares these, never text."""

    QUIET = "quiet"
    LIVELY = "lively"
    CENTRAL = "central"
    SECLUDED = "secluded"


HOTEL_ATMOSPHERE_SYNONYMS: dict[str, tuple[str, ...]] = {
    "quiet": ("peaceful", "yên tĩnh", "yên bình"),
    "lively": ("vibrant", "sôi động", "nhộn nhịp"),
    "central": ("downtown", "trung tâm"),
    "secluded": ("private", "biệt lập", "riêng tư"),
}
"""Governed display synonyms per normalized value, matched case-insensitively."""


@dataclass(frozen=True)
class SemanticKeyDefinition:
    """One code-reviewed registry entry projected into later layers."""

    key: str
    registry_version: str
    values: tuple[str, ...]
    cardinality: Cardinality | str
    allowed_scopes: tuple[MemoryScope, ...]
    minimum_sensitivity: SensitivityBand | str


HOTEL_ATMOSPHERE_DEFINITION = SemanticKeyDefinition(
    key=HOTEL_ATMOSPHERE_KEY,
    registry_version=SEMANTIC_REGISTRY_VERSION,
    values=tuple(member.value for member in HotelAtmosphere),
    cardinality=Cardinality.SINGLE,
    allowed_scopes=(MemoryScope.USER, MemoryScope.CONVERSATION),
    minimum_sensitivity=SensitivityBand.ORDINARY_PERSONAL,
)


class RegistryValidationError(ValueError):
    """One candidate field violates the governed registry entry."""

    def __init__(self, message: str = "Registry validation failed.", reason: str = ""):
        super().__init__(message)
        self.reason = reason


class UnknownKeyError(RegistryValidationError):
    """A semantic key is outside the governed registry."""

    def __init__(self, message: str = "Unknown semantic key."):
        super().__init__(message, reason="unknown_key")


class UnknownValueError(RegistryValidationError):
    """A value is outside the governed vocabulary of a known key."""

    def __init__(self, message: str = "Unknown semantic value."):
        super().__init__(message, reason="unknown_value")


def is_known_key(key: Any) -> bool:
    """Return whether one key is governed by this registry version."""
    return key == HOTEL_ATMOSPHERE_KEY


def get_key_definition(key: Any) -> SemanticKeyDefinition:
    """Return the registry entry for one key or reject the unknown key."""
    if key == HOTEL_ATMOSPHERE_KEY:
        return HOTEL_ATMOSPHERE_DEFINITION
    raise UnknownKeyError("Unknown semantic key.")


def normalize_value(key: Any, raw: Any) -> str:
    """Map one raw display string to its normalized registry value.

    Matching is whitespace-trimmed and case-insensitive over the
    normalized values and their governed synonyms. Unknown keys and
    unknown values raise; no guessing or partial matching occurs.
    """
    get_key_definition(key)
    if not isinstance(raw, str):
        raise UnknownValueError("A semantic value must be a string.")
    folded = raw.strip().casefold()
    if not folded:
        raise UnknownValueError("A semantic value must not be blank.")
    for member in HotelAtmosphere:
        if folded == member.value or folded in HOTEL_ATMOSPHERE_SYNONYMS[member.value]:
            return member.value
    raise UnknownValueError("A semantic value outside the governed vocabulary.")


def validate_against_registry(
    candidate: MemoryCandidate,
    definition: SemanticKeyDefinition | None = None,
) -> None:
    """Validate one candidate against its governed registry entry.

    Checks the canonical key, the normalized value membership, the
    scope allowance, the sensitivity floor, and the Phase-1 condition
    rule (no structured conditions yet). Returns nothing; violations
    raise a `RegistryValidationError` carrying a governed reason.
    """
    if not isinstance(candidate, MemoryCandidate):
        raise ValueError("validate_against_registry requires a MemoryCandidate.")
    resolved = (
        definition
        if definition is not None
        else get_key_definition(candidate.canonical_key)
    )
    if candidate.normalized_value not in resolved.values:
        raise UnknownValueError(
            "A semantic value outside the governed vocabulary for this key."
        )
    if candidate.scope not in resolved.allowed_scopes:
        raise RegistryValidationError(
            "A scope outside the governed scopes for this key.",
            reason="scope_not_allowed",
        )
    if (
        SENSITIVITY_RANK[candidate.sensitivity]
        < SENSITIVITY_RANK[resolved.minimum_sensitivity]
    ):
        raise RegistryValidationError(
            "A sensitivity below the governed floor for this key.",
            reason="sensitivity_below_floor",
        )
    if candidate.condition.strip():
        raise RegistryValidationError(
            "Structured conditions are not supported in this phase.",
            reason="condition_not_supported",
        )
