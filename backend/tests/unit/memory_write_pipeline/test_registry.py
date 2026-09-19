"""Unit tests for the versioned semantic registry.

`semantic-registry-v2` pins eight governed P0 Travel Agent keys, each with its
normalized values, cardinality, scopes, sensitivity floor, and bilingual
synonyms. The expected table below is written out independently of the
implementation so a key that quietly loses a value, a member, or a synonym
fails here rather than silently narrowing the product surface.

No test here touches a database, a model, HTTP, or the network.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.memory.write_pipeline.models import (
    Authority,
    Cardinality,
    MemoryCandidate,
    MemoryScope,
    SensitivityBand,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.registry import (
    HOTEL_ATMOSPHERE_DEFINITION,
    HOTEL_ATMOSPHERE_KEY,
    HOTEL_ATMOSPHERE_SYNONYMS,
    SEMANTIC_REGISTRY_VERSION,
    HotelAtmosphere,
    RegistryValidationError,
    SemanticKeyDefinition,
    UnknownKeyError,
    UnknownValueError,
    get_key_definition,
    is_known_key,
    normalize_value,
    registry_keys,
    validate_against_registry,
)

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)

#: The approved eight-key P0 slice, transcribed from `plan v0.11`. Values are in
#: the plan's order; cardinality is the plan's `Kind` column resolved.
_EXPECTED_REGISTRY = {
    "travel.preference.hotel_atmosphere": (
        Cardinality.SINGLE,
        ("quiet", "lively", "central", "secluded"),
    ),
    "travel.preference.accommodation_type": (
        Cardinality.SET,
        ("hotel", "resort", "hostel", "homestay", "apartment", "villa"),
    ),
    "travel.preference.transport_mode": (
        Cardinality.SET,
        (
            "flight",
            "train",
            "bus",
            "car",
            "motorbike",
            "public_transit",
            "walking",
        ),
    ),
    "travel.preference.travel_pace": (
        Cardinality.SINGLE,
        ("relaxed", "balanced", "packed"),
    ),
    "travel.preference.activity_style": (
        Cardinality.SET,
        (
            "nature",
            "culture",
            "food",
            "nightlife",
            "shopping",
            "adventure",
            "relaxation",
            "photography",
        ),
    ),
    "travel.constraint.budget_level": (
        Cardinality.SINGLE,
        ("budget", "midrange", "premium", "luxury"),
    ),
    "travel.preference.food_style": (
        Cardinality.SET,
        (
            "local",
            "street_food",
            "fine_dining",
            "cafe",
            "vegetarian_friendly",
            "international",
        ),
    ),
    "travel.profile.default_departure_city": (
        Cardinality.SINGLE,
        (
            "ho_chi_minh_city",
            "hanoi",
            "da_nang",
            "can_tho",
            "hai_phong",
            "nha_trang",
            "hue",
            "phu_quoc",
        ),
    ),
}


def _valid_candidate(**overrides) -> MemoryCandidate:
    payload = {
        "candidate_id": new_candidate_id(),
        "evidence_ids": (new_evidence_id(),),
        "owner_user_id": "user_owner",
        "scope": MemoryScope.USER,
        "conversation_id": None,
        "canonical_key": HOTEL_ATMOSPHERE_KEY,
        "normalized_value": "quiet",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_SAVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "observed_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _narrow_definition(**overrides) -> SemanticKeyDefinition:
    payload = {
        "key": HOTEL_ATMOSPHERE_KEY,
        "registry_version": SEMANTIC_REGISTRY_VERSION,
        "values": ("quiet", "lively", "central", "secluded"),
        "cardinality": Cardinality.SINGLE,
        "allowed_scopes": (MemoryScope.USER, MemoryScope.CONVERSATION),
        "minimum_sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "synonyms": {"quiet": ("peaceful",)},
    }
    payload.update(overrides)
    return SemanticKeyDefinition(**payload)


def test_registry_version_is_pinned():
    assert SEMANTIC_REGISTRY_VERSION == "semantic-registry-v2"


def test_the_registry_has_exactly_the_eight_approved_keys():
    """Eight, not "at least eight".

    The first version of this test looked up each expected key and never asked
    whether the registry held *more* — so a ninth key added without an amendment
    passed. A registry that can grow silently is not a closed contract, and an
    unreviewed value vocabulary would reach durable storage.
    """
    assert len(registry_keys()) == 8
    assert set(registry_keys()) == set(_EXPECTED_REGISTRY)


def test_every_governed_key_is_present_with_its_approved_shape():
    """Each approved key carries exactly its approved cardinality and values."""
    for key, (cardinality, values) in _EXPECTED_REGISTRY.items():
        definition = get_key_definition(key)

        assert definition.cardinality is cardinality, key
        assert definition.values == values, key


def test_every_governed_key_allows_both_scopes_and_the_ordinary_floor():
    """All eight entries allow user scope plus conversation override."""
    for key in _EXPECTED_REGISTRY:
        definition = get_key_definition(key)

        assert set(definition.allowed_scopes) == {
            MemoryScope.USER,
            MemoryScope.CONVERSATION,
        }, key
        assert definition.minimum_sensitivity is (
            SensitivityBand.ORDINARY_PERSONAL
        ), key


def test_every_value_carries_at_least_one_synonym_and_none_is_empty():
    """Governed synonyms are part of the entry, not a separate lookup table."""
    for key in _EXPECTED_REGISTRY:
        definition = get_key_definition(key)

        assert set(definition.synonyms) == set(definition.values), key
        for value, synonyms in definition.synonyms.items():
            assert synonyms, f"{key}/{value} has no governed synonyms"


def test_every_governed_value_normalizes_to_itself():
    """Round trip: the canonical member is always accepted as input."""
    for key, (cardinality, values) in _EXPECTED_REGISTRY.items():
        for value in values:
            normalized = normalize_value(key, value)
            if cardinality is Cardinality.SINGLE:
                assert normalized == value
            else:
                assert normalized == (value,)


def test_a_set_key_normalizes_a_collection_to_a_sorted_deduplicated_tuple():
    """Order and duplication are collapsed, deterministically.

    Two extraction runs that saw the same members in different orders must
    produce the same stored snapshot, and a member seen twice is one member.
    """
    key = "travel.preference.activity_style"

    assert normalize_value(key, ["food", "culture", "food"]) == ("culture", "food")
    assert normalize_value(key, ("culture", "food")) == ("culture", "food")
    assert normalize_value(key, "FOOD") == ("food",)
    assert normalize_value(key, ["ăn uống"]) == ("food",)


def test_a_set_key_rejects_an_empty_collection():
    """An empty set is a revoke, and a revoke is not a normalized value."""
    with pytest.raises(UnknownValueError):
        normalize_value("travel.preference.activity_style", [])


def test_a_single_key_refuses_a_collection():
    """A single key holds one value; a collection is a different cardinality."""
    with pytest.raises(UnknownValueError):
        normalize_value(HOTEL_ATMOSPHERE_KEY, ["quiet", "lively"])


def test_a_set_key_rejects_one_unknown_member():
    """One bad member rejects the whole collection rather than being dropped."""
    with pytest.raises(UnknownValueError):
        normalize_value("travel.preference.activity_style", ["food", "beachfront"])


def test_registry_definition_is_immutable_to_callers():
    """A caller cannot mutate a governed definition in place."""
    definition = get_key_definition(HOTEL_ATMOSPHERE_KEY)

    with pytest.raises((TypeError, AttributeError)):
        definition.synonyms["quiet"] = ("tampered",)  # type: ignore[index]


def test_imported_hotel_constants_are_aliases_into_registry_v2():
    """The compatibility constants resolve to the same governed data.

    `plan v0.11`: they remain aliases during Task 6 and must not own separate
    values, normalization logic, or a special execution branch.
    """
    assert HOTEL_ATMOSPHERE_KEY in _EXPECTED_REGISTRY
    assert HOTEL_ATMOSPHERE_DEFINITION is get_key_definition(HOTEL_ATMOSPHERE_KEY)
    assert {member.value for member in HotelAtmosphere} == set(
        HOTEL_ATMOSPHERE_DEFINITION.values
    )


def test_the_synonym_alias_is_the_definition_data_not_a_copy():
    """One source of truth: the alias *is* the definition's mapping.

    The first version built a fresh `dict` from the definition, which is a
    second copy that can drift and that a caller can mutate. Identity, not
    equality, is the property that rules that out.
    """
    assert HOTEL_ATMOSPHERE_SYNONYMS is HOTEL_ATMOSPHERE_DEFINITION.synonyms


def test_the_synonym_alias_cannot_be_mutated():
    """A caller must not be able to widen the governed vocabulary at runtime."""
    with pytest.raises(TypeError):
        HOTEL_ATMOSPHERE_SYNONYMS["quiet"] = ("tampered",)  # type: ignore[index]

    with pytest.raises(TypeError):
        HOTEL_ATMOSPHERE_SYNONYMS["invented"] = ("tampered",)  # type: ignore[index]


def test_the_hotel_value_enum_derives_from_the_definition():
    """`HotelAtmosphere` declares no vocabulary of its own.

    Built from the definition's values rather than written out, so the enum and
    the registry cannot disagree about which hotel atmospheres exist.
    """
    assert tuple(member.value for member in HotelAtmosphere) == (
        HOTEL_ATMOSPHERE_DEFINITION.values
    )
    for member in HotelAtmosphere:
        assert member.value in HOTEL_ATMOSPHERE_DEFINITION.values
        assert normalize_value(HOTEL_ATMOSPHERE_KEY, member.value) == member.value


def test_the_hotel_synonyms_are_the_ones_the_registry_normalizes():
    """Every governed synonym actually normalizes to its value.

    Asserting the mapping exists is weaker than asserting the registry answers
    with it, which is what a caller of the alias depends on.
    """
    for value, synonyms in HOTEL_ATMOSPHERE_SYNONYMS.items():
        for synonym in synonyms:
            assert normalize_value(HOTEL_ATMOSPHERE_KEY, synonym) == value


def test_first_key_is_exact():
    assert HOTEL_ATMOSPHERE_KEY == "travel.preference.hotel_atmosphere"


def test_first_key_has_exactly_four_normalized_values():
    assert {member.value for member in HotelAtmosphere} == {
        "quiet",
        "lively",
        "central",
        "secluded",
    }


def test_first_key_is_single_cardinality():
    definition = get_key_definition(HOTEL_ATMOSPHERE_KEY)
    assert definition.cardinality is Cardinality.SINGLE


def test_first_key_allows_user_and_conversation_scopes():
    definition = get_key_definition(HOTEL_ATMOSPHERE_KEY)
    assert set(definition.allowed_scopes) == {
        MemoryScope.USER,
        MemoryScope.CONVERSATION,
    }


def test_first_key_minimum_sensitivity_is_ordinary_personal():
    definition = get_key_definition(HOTEL_ATMOSPHERE_KEY)
    assert definition.minimum_sensitivity is SensitivityBand.ORDINARY_PERSONAL


def test_authority_order_is_explicit_save_first():
    from backend.memory.write_pipeline.models import AUTHORITY_RANK

    assert (
        AUTHORITY_RANK[Authority.EXPLICIT_SAVE]
        > AUTHORITY_RANK[Authority.EXPLICIT_STATEMENT]
        > AUTHORITY_RANK[Authority.REPEATED_INFERENCE]
    )


def test_normalize_accepts_exact_values_case_and_whitespace_insensitive():
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "quiet") == "quiet"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "  LIVELY ") == "lively"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "Central") == "central"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "SECLUDED") == "secluded"


def test_normalize_accepts_vietnamese_synonyms():
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "yên tĩnh") == "quiet"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "sôi động") == "lively"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "trung tâm") == "central"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "biệt lập") == "secluded"


def test_normalize_accepts_english_synonyms():
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "peaceful") == "quiet"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "vibrant") == "lively"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "downtown") == "central"
    assert normalize_value(HOTEL_ATMOSPHERE_KEY, "private") == "secluded"


def test_normalize_rejects_unknown_value():
    with pytest.raises(UnknownValueError):
        normalize_value(HOTEL_ATMOSPHERE_KEY, "beachfront")


def test_normalize_rejects_unknown_key():
    with pytest.raises(UnknownKeyError):
        normalize_value("travel.preference.unknown_key", "quiet")


def test_unknown_key_lookup_is_rejected():
    assert is_known_key(HOTEL_ATMOSPHERE_KEY) is True
    assert is_known_key("travel.preference.unknown_key") is False
    with pytest.raises(UnknownKeyError):
        get_key_definition("travel.preference.unknown_key")


def test_registry_definition_carries_its_version():
    definition = get_key_definition(HOTEL_ATMOSPHERE_KEY)
    assert definition.registry_version == SEMANTIC_REGISTRY_VERSION
    assert definition.key == HOTEL_ATMOSPHERE_KEY


# Validator: key, value, scope, sensitivity floor, and Phase-1 condition rule.


def test_validator_accepts_a_governed_candidate():
    assert validate_against_registry(_valid_candidate()) is None


def test_validator_rejects_unknown_key():
    with pytest.raises(UnknownKeyError):
        validate_against_registry(
            _valid_candidate(canonical_key="travel.preference.unknown_key")
        )


def test_validator_rejects_unknown_value():
    with pytest.raises(UnknownValueError):
        validate_against_registry(_valid_candidate(normalized_value="beachfront"))


def test_validator_rejects_non_empty_condition():
    with pytest.raises(RegistryValidationError) as excinfo:
        validate_against_registry(_valid_candidate(condition="near the beach"))
    assert excinfo.value.reason == "condition_not_supported"


def test_validator_enforces_scope_allowance():
    narrow = _narrow_definition(allowed_scopes=(MemoryScope.USER,))
    scoped = _valid_candidate(scope=MemoryScope.CONVERSATION, conversation_id="cv_x")
    with pytest.raises(RegistryValidationError) as excinfo:
        validate_against_registry(scoped, definition=narrow)
    assert excinfo.value.reason == "scope_not_allowed"


def test_validator_enforces_sensitivity_floor():
    narrow = _narrow_definition(minimum_sensitivity=SensitivityBand.RESTRICTED)
    with pytest.raises(RegistryValidationError) as excinfo:
        validate_against_registry(_valid_candidate(), definition=narrow)
    assert excinfo.value.reason == "sensitivity_below_floor"


def test_validator_accepts_a_governed_set_candidate():
    candidate = _valid_candidate(
        canonical_key="travel.preference.activity_style",
        normalized_value=("culture", "food"),
    )

    assert validate_against_registry(candidate) is None


def test_validator_rejects_a_set_member_outside_the_entry():
    """The snapshot is ascending so it reaches the registry check at all.

    `("beachfront", "culture")` is a well-formed snapshot of two members; only
    the registry can say that one of them is not a governed value.
    """
    candidate = _valid_candidate(
        canonical_key="travel.preference.activity_style",
        normalized_value=("beachfront", "culture"),
    )

    with pytest.raises(UnknownValueError):
        validate_against_registry(candidate)


def test_validator_rejects_a_value_shape_that_contradicts_cardinality():
    """A tuple for a single key, or a bare string for a set key, is refused.

    The value shape is what the persistence layer keys its encoding off, so a
    mismatch here would be discovered as a storage defect instead of as a
    contract violation.
    """
    with pytest.raises(UnknownValueError):
        validate_against_registry(_valid_candidate(normalized_value=("quiet",)))

    with pytest.raises(UnknownValueError):
        validate_against_registry(
            _valid_candidate(
                canonical_key="travel.preference.activity_style",
                normalized_value="culture",
            )
        )


def test_no_stale_single_key_claim_survives_in_the_registry():
    """The module no longer describes a one-key registry."""
    source = (
        Path(__file__).resolve().parents[4]
        / "backend/memory/write_pipeline/registry.py"
    ).read_text(encoding="utf-8")

    assert "the first canonical key" not in source
