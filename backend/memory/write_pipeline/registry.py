"""Versioned semantic registry: `semantic-registry-v2`.

Eight governed P0 Travel Agent keys, each owning its normalized values,
cardinality, allowed scopes, sensitivity floor, and per-value English/Vietnamese
synonyms. Lookup and normalization are **data-driven over these definitions**:
there is no hotel-specific execution branch left, and the former single-key
constants survive only as aliases into the same data (`plan v0.11`).

Two rules the shapes here exist to enforce:

- The registry is a **closed contract**. Unknown keys and unknown values raise;
  nothing is guessed, prefix-matched, or partially matched.
- A `set` key carries a canonical, sorted, deduplicated tuple. The representation
  is declared, never inferred from a delimiter, so no reader has to decide
  whether `"a|b"` is one value or two.

This module depends on the Python standard library and the sibling contract
module only.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any

from backend.memory.write_pipeline.models import (
    SENSITIVITY_RANK,
    Cardinality,
    MemoryCandidate,
    MemoryScope,
    NormalizedSemanticValue,
    SensitivityBand,
)

SEMANTIC_REGISTRY_VERSION = "semantic-registry-v2"

HOTEL_ATMOSPHERE_KEY = "travel.preference.hotel_atmosphere"


@dataclass(frozen=True)
class SemanticKeyDefinition:
    """One code-reviewed registry entry projected into later layers.

    `synonyms` is per normalized value, so a value and the words that mean it
    travel together. It is exposed read-only: a caller that could mutate a
    definition in place could widen the governed vocabulary at runtime.
    """

    key: str
    registry_version: str
    values: tuple[str, ...]
    cardinality: Cardinality | str
    allowed_scopes: tuple[MemoryScope, ...]
    minimum_sensitivity: SensitivityBand | str
    synonyms: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "synonyms",
            MappingProxyType(
                {value: tuple(words) for value, words in self.synonyms.items()}
            ),
        )


def _definition(
    key: str,
    cardinality: Cardinality,
    synonyms: dict[str, tuple[str, ...]],
) -> SemanticKeyDefinition:
    """Build one entry, deriving `values` from the synonym table's keys.

    Deriving rather than repeating means a value cannot exist in the vocabulary
    without also having governed synonyms, which is the property the registry
    tests pin.
    """
    return SemanticKeyDefinition(
        key=key,
        registry_version=SEMANTIC_REGISTRY_VERSION,
        values=tuple(synonyms),
        cardinality=cardinality,
        allowed_scopes=(MemoryScope.USER, MemoryScope.CONVERSATION),
        minimum_sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        synonyms=synonyms,
    )


_HOTEL_ATMOSPHERE_SYNONYMS = {
    "quiet": ("peaceful", "calm", "yên tĩnh", "yên bình"),
    "lively": ("vibrant", "bustling", "sôi động", "nhộn nhịp"),
    "central": ("downtown", "trung tâm"),
    "secluded": ("private", "biệt lập", "riêng tư"),
}

_ACCOMMODATION_TYPE_SYNONYMS = {
    "hotel": ("khách sạn",),
    "resort": ("khu nghỉ dưỡng",),
    "hostel": ("nhà nghỉ", "kí túc xá"),
    "homestay": ("nhà dân", "ở cùng gia đình"),
    "apartment": ("căn hộ",),
    "villa": ("biệt thự",),
}

_TRANSPORT_MODE_SYNONYMS = {
    "flight": ("plane", "máy bay", "hàng không"),
    "train": ("tàu hỏa", "tàu"),
    "bus": ("coach", "xe buýt", "xe khách"),
    "car": ("ô tô", "xe hơi"),
    "motorbike": ("motorcycle", "scooter", "xe máy"),
    "public_transit": ("public transport", "giao thông công cộng"),
    "walking": ("walk", "đi bộ"),
}

_TRAVEL_PACE_SYNONYMS = {
    "relaxed": ("slow", "thư giãn", "chậm rãi"),
    "balanced": ("moderate", "cân bằng", "vừa phải"),
    "packed": ("intense", "dày đặc", "kín lịch"),
}

_ACTIVITY_STYLE_SYNONYMS = {
    "nature": ("thiên nhiên",),
    "culture": ("văn hóa",),
    "food": ("cuisine", "ẩm thực", "ăn uống"),
    "nightlife": ("cuộc sống về đêm",),
    "shopping": ("mua sắm",),
    "adventure": ("phiêu lưu", "mạo hiểm"),
    "relaxation": ("thư giãn", "nghỉ ngơi"),
    "photography": ("chụp ảnh", "nhiếp ảnh"),
}

_BUDGET_LEVEL_SYNONYMS = {
    "budget": ("cheap", "tiết kiệm", "bình dân"),
    "midrange": ("moderate", "tầm trung"),
    "premium": ("cao cấp",),
    "luxury": ("sang trọng", "hạng sang"),
}

_FOOD_STYLE_SYNONYMS = {
    "local": ("địa phương", "món địa phương"),
    "street_food": ("đồ ăn đường phố", "quán vỉa hè"),
    "fine_dining": ("nhà hàng cao cấp",),
    "cafe": ("coffee", "cà phê", "quán cà phê"),
    "vegetarian_friendly": ("vegetarian", "ăn chay"),
    "international": ("quốc tế",),
}

_DEFAULT_DEPARTURE_CITY_SYNONYMS = {
    "ho_chi_minh_city": ("hồ chí minh", "sài gòn", "tp hcm", "hcm"),
    "hanoi": ("hà nội",),
    "da_nang": ("đà nẵng",),
    "can_tho": ("cần thơ",),
    "hai_phong": ("hải phòng",),
    "nha_trang": ("nha trang",),
    "hue": ("huế",),
    "phu_quoc": ("phú quốc",),
}

_DEFINITIONS: dict[str, SemanticKeyDefinition] = {
    definition.key: definition
    for definition in (
        _definition(
            HOTEL_ATMOSPHERE_KEY, Cardinality.SINGLE, _HOTEL_ATMOSPHERE_SYNONYMS
        ),
        _definition(
            "travel.preference.accommodation_type",
            Cardinality.SET,
            _ACCOMMODATION_TYPE_SYNONYMS,
        ),
        _definition(
            "travel.preference.transport_mode",
            Cardinality.SET,
            _TRANSPORT_MODE_SYNONYMS,
        ),
        _definition(
            "travel.preference.travel_pace", Cardinality.SINGLE, _TRAVEL_PACE_SYNONYMS
        ),
        _definition(
            "travel.preference.activity_style",
            Cardinality.SET,
            _ACTIVITY_STYLE_SYNONYMS,
        ),
        _definition(
            "travel.constraint.budget_level",
            Cardinality.SINGLE,
            _BUDGET_LEVEL_SYNONYMS,
        ),
        _definition(
            "travel.preference.food_style", Cardinality.SET, _FOOD_STYLE_SYNONYMS
        ),
        _definition(
            "travel.profile.default_departure_city",
            Cardinality.SINGLE,
            _DEFAULT_DEPARTURE_CITY_SYNONYMS,
        ),
    )
}

# --- Compatibility aliases -------------------------------------------------
#
# Current callers import these. They are views onto the definitions above, not a
# second source of truth: the definition *is* the registry entry, the enum is
# built from that entry's values, and the synonym mapping *is* that entry's
# mapping — so none of them can drift from registry-v2.

HOTEL_ATMOSPHERE_DEFINITION = _DEFINITIONS[HOTEL_ATMOSPHERE_KEY]

HotelAtmosphere = Enum(
    "HotelAtmosphere",
    {
        value.upper(): value
        for value in HOTEL_ATMOSPHERE_DEFINITION.values
    },
    type=str,
    module=__name__,
)
"""Compatibility alias for the `hotel_atmosphere` value vocabulary.

Built from the definition rather than written out, so this enum cannot disagree
with the registry about which hotel atmospheres exist.
"""

HOTEL_ATMOSPHERE_SYNONYMS: Mapping[str, tuple[str, ...]] = (
    HOTEL_ATMOSPHERE_DEFINITION.synonyms
)
"""The definition's own synonym mapping, not a copy of it.

Read-only by construction (`MappingProxyType`), so a caller cannot widen the
governed vocabulary at runtime, and there is exactly one place the words live.
"""


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


def registry_keys() -> tuple[str, ...]:
    """Return every governed key, in registry order."""
    return tuple(_DEFINITIONS)


def is_known_key(key: Any) -> bool:
    """Return whether one key is governed by this registry version."""
    return isinstance(key, str) and key in _DEFINITIONS


def get_key_definition(key: Any) -> SemanticKeyDefinition:
    """Return the registry entry for one key or reject the unknown key."""
    if isinstance(key, str) and key in _DEFINITIONS:
        return _DEFINITIONS[key]
    raise UnknownKeyError("Unknown semantic key.")


def _folded(raw: Any) -> str:
    if not isinstance(raw, str):
        raise UnknownValueError("A semantic value must be a string.")
    folded = raw.strip().casefold()
    if not folded:
        raise UnknownValueError("A semantic value must not be blank.")
    return folded


def _member_for(definition: SemanticKeyDefinition, raw: Any) -> str:
    """Map one raw display string to its normalized member, or raise."""
    folded = _folded(raw)
    for value in definition.values:
        if folded == value.casefold():
            return value
        if any(folded == word.casefold() for word in definition.synonyms[value]):
            return value
    raise UnknownValueError("A semantic value outside the governed vocabulary.")


def _collection(raw: Any) -> list[Any] | None:
    """Return the raw value as a list when it is a non-string collection."""
    if isinstance(raw, str):
        return None
    if isinstance(raw, Iterable):
        return list(raw)
    return None


def normalize_value(key: Any, raw: Any) -> NormalizedSemanticValue:
    """Map raw display input to its governed normalized value(s).

    Matching is whitespace-trimmed and case-insensitive over the normalized
    values and their governed synonyms. Unknown keys and unknown values raise;
    no guessing or partial matching occurs.

    For a `single` key the result is one `str`, and a collection is refused
    because it is a different cardinality. For a `set` key the result is always
    a tuple — a single member normalizes to a one-member tuple — sorted and
    deduplicated, so two runs that saw the same members in different orders
    produce the same snapshot.
    """
    definition = get_key_definition(key)
    if definition.cardinality is not Cardinality.SET:
        if _collection(raw) is not None:
            raise UnknownValueError(
                "A single-cardinality key holds one value, not a collection."
            )
        return _member_for(definition, raw)

    members = _collection(raw)
    if members is None:
        members = [raw]
    if not members:
        raise UnknownValueError("An empty set is a revoke, not a governed value.")
    return tuple(sorted({_member_for(definition, member) for member in members}))


def validate_against_registry(
    candidate: MemoryCandidate,
    definition: SemanticKeyDefinition | None = None,
) -> None:
    """Validate one candidate against its governed registry entry.

    Checks the canonical key, the value's shape against the entry's cardinality,
    membership of every member, the scope allowance, the sensitivity floor, and
    the Phase-1 condition rule (no structured conditions yet). Returns nothing;
    violations raise a `RegistryValidationError` carrying a governed reason.
    """
    if not isinstance(candidate, MemoryCandidate):
        raise ValueError("validate_against_registry requires a MemoryCandidate.")
    resolved = (
        definition
        if definition is not None
        else get_key_definition(candidate.canonical_key)
    )
    value = candidate.normalized_value
    if resolved.cardinality is Cardinality.SET:
        if not isinstance(value, tuple):
            raise UnknownValueError(
                "A set-cardinality key requires a tuple of governed members."
            )
        if any(member not in resolved.values for member in value):
            raise UnknownValueError(
                "A semantic value outside the governed vocabulary for this key."
            )
    else:
        if not isinstance(value, str):
            raise UnknownValueError(
                "A single-cardinality key requires one governed string value."
            )
        if value not in resolved.values:
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
