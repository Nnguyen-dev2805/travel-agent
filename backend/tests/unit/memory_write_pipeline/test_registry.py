"""Unit tests for the versioned semantic registry (first canonical key).

The registry pins the exact key, normalized values, cardinality, scopes,
sensitivity floor, and bilingual synonyms for
`travel.preference.hotel_atmosphere`. No test here touches a database, a
model, HTTP, or the network.
"""

from datetime import datetime, timezone

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
    HOTEL_ATMOSPHERE_KEY,
    SEMANTIC_REGISTRY_VERSION,
    HotelAtmosphere,
    RegistryValidationError,
    SemanticKeyDefinition,
    UnknownKeyError,
    UnknownValueError,
    get_key_definition,
    is_known_key,
    normalize_value,
    validate_against_registry,
)

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)


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
    }
    payload.update(overrides)
    return SemanticKeyDefinition(**payload)


def test_registry_version_is_pinned():
    assert SEMANTIC_REGISTRY_VERSION == "semantic-registry-v1"


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
