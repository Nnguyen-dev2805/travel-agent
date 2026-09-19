"""Unit tests for MemoryReadEngine and MemoryReadRequest truth table."""
from datetime import datetime, timedelta, timezone

import pytest

from backend.memory.lifecycle import SourceValidity
from backend.memory.read_engine import MemoryReadEngine
from backend.memory.read_models import (
    AbstentionReason,
    MemoryReadRequest,
    StoredMemoryRow,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self, rows):
        self.rows = rows

    def list_storage_scoped(self, request):
        return self.rows


def _engine(rows, clock=None):
    return MemoryReadEngine(Store(rows), clock=clock or (lambda: NOW))


def _row(**overrides):
    value = dict(
        version_id="mem_1",
        canonical_key="travel.preference.hotel_atmosphere",
        normalized_value="quiet",
        owner_user_id="owner",
        scope=MemoryScope.USER,
        scope_id="owner",
        authority=Authority.EXPLICIT_SAVE,
        valid_from=NOW,
        retention_mode=RetentionMode.USER_DURABLE,
        stamped_generation=1,
        current_generation=1,
        status=VersionStatus.ACTIVE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        source_validity=SourceValidity.NOT_REQUIRED,
        expires_at=None,
        unresolved_conflict=False,
    )
    value.update(overrides)
    return StoredMemoryRow(**value)


# --- Request validation tests ---


def test_request_rejects_more_than_registry_cap():
    with pytest.raises(ValueError, match="max_selected"):
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
            max_selected=9,
        )


def test_request_rejects_bool_max_selected():
    with pytest.raises(ValueError, match="max_selected"):
        MemoryReadRequest(owner_user_id="owner", max_selected=True)


def test_request_rejects_max_selected_zero():
    with pytest.raises(ValueError, match="max_selected"):
        MemoryReadRequest(owner_user_id="owner", max_selected=0)


def test_request_rejects_max_selected_negative():
    with pytest.raises(ValueError, match="max_selected"):
        MemoryReadRequest(owner_user_id="owner", max_selected=-1)


def test_request_rejects_empty_owner_user_id():
    with pytest.raises(ValueError, match="owner_user_id"):
        MemoryReadRequest(owner_user_id="")
    with pytest.raises(ValueError, match="owner_user_id"):
        MemoryReadRequest(owner_user_id="   ")


def test_request_rejects_duplicate_keys():
    with pytest.raises(ValueError, match="repeat"):
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=(
                "travel.preference.hotel_atmosphere",
                "travel.preference.hotel_atmosphere",
            ),
        )


def test_request_rejects_unknown_registry_key():
    with pytest.raises(ValueError, match="Unknown semantic key"):
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("invalid.unknown.key",),
        )


# --- Abstention & Lifecycle truth table tests ---


def test_engine_abstains_when_requested_keys_are_empty():
    result = _engine((_row(),)).select(MemoryReadRequest(owner_user_id="owner"))
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_REQUESTED_KEYS


def test_engine_rejects_revoked_row():
    result = _engine((_row(status=VersionStatus.REVOKED),)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_superseded_row():
    result = _engine((_row(status=VersionStatus.SUPERSEDED),)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_expired_row():
    past = NOW - timedelta(seconds=1)
    result = _engine((_row(expires_at=past),)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_stale_generation_row():
    result = _engine(
        (_row(stamped_generation=1, current_generation=2),)
    ).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_invalid_source_row():
    result = _engine(
        (
            _row(
                retention_mode=RetentionMode.SOURCE_BOUND,
                source_validity=SourceValidity.INVALID,
            ),
        )
    ).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_sensitivity_blocked_row():
    result = _engine(
        (_row(sensitivity=SensitivityBand.PROHIBITED_SECRET),)
    ).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_foreign_owner_row():
    result = _engine((_row(owner_user_id="foreign_owner"),)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_rejects_unmatched_conversation_id():
    result = _engine(
        (
            _row(
                scope=MemoryScope.CONVERSATION,
                scope_id="cv_2",
                retention_mode=RetentionMode.CONVERSATION_BOUND,
                source_validity=SourceValidity.VALID,
            ),
        )
    ).select(
        MemoryReadRequest(
            owner_user_id="owner",
            conversation_id="cv_1",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


# --- Conflict suppression tests ---


def test_engine_suppresses_whole_key_on_unresolved_conflict():
    row_active = _row(
        version_id="mem_clean",
        canonical_key="travel.preference.hotel_atmosphere",
        unresolved_conflict=False,
    )
    row_conflict = _row(
        version_id="mem_conflicted",
        canonical_key="travel.preference.hotel_atmosphere",
        unresolved_conflict=True,
    )
    result = _engine((row_active, row_conflict)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=("travel.preference.hotel_atmosphere",),
        )
    )
    assert result.selected == ()
    assert result.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY


def test_engine_does_not_suppress_unrelated_key_on_conflict():
    row_conflicted = _row(
        version_id="mem_1",
        canonical_key="travel.preference.hotel_atmosphere",
        unresolved_conflict=True,
    )
    row_clean = _row(
        version_id="mem_2",
        canonical_key="travel.preference.travel_pace",
        normalized_value="relaxed",
        unresolved_conflict=False,
    )
    result = _engine((row_conflicted, row_clean)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=(
                "travel.preference.hotel_atmosphere",
                "travel.preference.travel_pace",
            ),
        )
    )
    assert len(result.selected) == 1
    assert result.selected[0].canonical_key == "travel.preference.travel_pace"
    assert result.selected[0].normalized_value == "relaxed"
    assert result.abstention_reason is None


# --- Precedence & Ordering tests ---


def test_conversation_scope_overrides_same_user_key_without_mutating_it():
    user = _row(version_id="mem_user", valid_from=NOW)
    conversation = _row(
        version_id="mem_conversation",
        normalized_value="lively",
        scope=MemoryScope.CONVERSATION,
        scope_id="cv_1",
        retention_mode=RetentionMode.CONVERSATION_BOUND,
        source_validity=SourceValidity.VALID,
    )
    result = _engine((user, conversation)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            conversation_id="cv_1",
            requested_keys=("travel.preference.hotel_atmosphere",),
        ),
    )
    assert tuple(item.version_id for item in result.selected) == ("mem_conversation",)
    assert user.normalized_value == "quiet"


def test_engine_deterministic_ordering():
    # valid_from DESC -> canonical_key ASC -> version_id ASC
    t_older = NOW - timedelta(hours=1)
    row_old = _row(
        version_id="mem_old",
        canonical_key="travel.preference.hotel_atmosphere",
        valid_from=t_older,
    )
    row_pace = _row(
        version_id="mem_pace",
        canonical_key="travel.preference.travel_pace",
        valid_from=NOW,
    )
    row_hotel_b = _row(
        version_id="mem_b",
        canonical_key="travel.preference.hotel_atmosphere",
        valid_from=NOW,
    )
    row_hotel_a = _row(
        version_id="mem_a",
        canonical_key="travel.preference.hotel_atmosphere",
        valid_from=NOW,
    )

    result = _engine((row_old, row_pace, row_hotel_b, row_hotel_a)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=(
                "travel.preference.hotel_atmosphere",
                "travel.preference.travel_pace",
            ),
        )
    )
    selected_ids = tuple(item.version_id for item in result.selected)
    # NOW items first:
    # canonical_key hotel_atmosphere < travel_pace:
    # among hotel_atmosphere at NOW: mem_a < mem_b -> mem_a, mem_b
    # then travel_pace at NOW: mem_pace
    # then hotel_atmosphere at t_older: mem_old
    assert selected_ids == ("mem_a", "mem_b", "mem_pace", "mem_old")


def test_engine_truncates_to_max_selected():
    row1 = _row(
        version_id="mem_1",
        canonical_key="travel.preference.hotel_atmosphere",
        valid_from=NOW,
    )
    row2 = _row(
        version_id="mem_2",
        canonical_key="travel.preference.travel_pace",
        valid_from=NOW,
    )
    row3 = _row(
        version_id="mem_3",
        canonical_key="travel.constraint.budget_level",
        valid_from=NOW,
    )
    result = _engine((row1, row2, row3)).select(
        MemoryReadRequest(
            owner_user_id="owner",
            max_selected=2,
            requested_keys=(
                "travel.preference.hotel_atmosphere",
                "travel.preference.travel_pace",
                "travel.constraint.budget_level",
            ),
        )
    )
    assert len(result.selected) == 2
    assert result.abstention_reason is None


def test_engine_default_clock_supports_timezone_aware_expires_at():
    # Verify default clock (clock=None) handles timezone-aware expires_at without TypeError
    future_time = datetime.now(timezone.utc) + timedelta(hours=1)
    past_time = datetime.now(timezone.utc) - timedelta(hours=1)

    future_row = _row(
        version_id="mem_future",
        canonical_key="travel.preference.hotel_atmosphere",
        expires_at=future_time,
    )
    past_row = _row(
        version_id="mem_past",
        canonical_key="travel.preference.travel_pace",
        expires_at=past_time,
    )

    # Instantiate engine with default clock (clock=None)
    engine = MemoryReadEngine(Store((future_row, past_row)))
    result = engine.select(
        MemoryReadRequest(
            owner_user_id="owner",
            requested_keys=(
                "travel.preference.hotel_atmosphere",
                "travel.preference.travel_pace",
            ),
        )
    )
    # future_row selected, past_row expired
    assert [s.version_id for s in result.selected] == ["mem_future"]


def test_request_coerces_list_to_tuple():
    req = MemoryReadRequest(
        owner_user_id="owner",
        requested_keys=["travel.preference.hotel_atmosphere"],  # type: ignore[arg-type]
    )
    assert isinstance(req.requested_keys, tuple)
    assert req.requested_keys == ("travel.preference.hotel_atmosphere",)

