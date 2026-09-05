"""Unit tests for R7 planner domain contracts.

Tests assert id prefixes, text stripping and limits, positive version/day
position values, UTC datetimes, typed itinerary items, and the decision
updated_at invariant. No test touches a real database, a model provider,
Chroma, or the network.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersion,
    ItineraryVersionDraft,
    PlannerOperation,
    PlannerOperationStatus,
    PlannerOperationType,
    PlannerValidationError,
    TripDecision,
    generate_decision_id,
    generate_itinerary_version_id,
    generate_operation_id,
)

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def _item(**overrides):
    payload = {
        "day_index": 1,
        "position": 1,
        "item_type": ItineraryItemType.MEAL,
        "title": "Bún chả Hương Liên",
        "location": "Hà Nội",
        "start_time": "19:00",
        "end_time": "20:30",
        "notes": None,
        "source_decision_ids": (),
    }
    payload.update(overrides)
    return ItineraryItem(**payload)


def _version(**overrides):
    payload = {
        "itinerary_version_id": generate_itinerary_version_id(),
        "workspace_id": "tw_planner",
        "version_number": 1,
        "status": ItineraryStatus.DRAFT,
        "title": "Hà Nội 3 ngày",
        "summary": None,
        "items": (_item(),),
        "created_from_operation_id": None,
        "created_from_message_id": None,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return ItineraryVersion(**payload)


def _decision(**overrides):
    payload = {
        "decision_id": generate_decision_id(),
        "workspace_id": "tw_planner",
        "decision_type": DecisionType.PREFERENCE,
        "status": DecisionStatus.PENDING,
        "statement": "Chuyến này ăn chay.",
        "rationale": None,
        "source_message_id": None,
        "supersedes_decision_id": None,
        "created_at": MOMENT,
        "updated_at": MOMENT,
    }
    payload.update(overrides)
    return TripDecision(**payload)


def _operation(**overrides):
    payload = {
        "operation_id": generate_operation_id(),
        "workspace_id": "tw_planner",
        "conversation_id": None,
        "operation_type": PlannerOperationType.CREATE_ITINERARY,
        "status": PlannerOperationStatus.APPLIED,
        "input_summary": None,
        "result_itinerary_version_id": None,
        "result_decision_id": None,
        "source_message_id": None,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return PlannerOperation(**payload)


def _draft(**overrides):
    payload = {
        "workspace_id": "tw_planner",
        "status": ItineraryStatus.DRAFT,
        "title": "Hà Nội 3 ngày",
        "summary": None,
        "items": (),
        "created_from_operation_id": None,
        "created_from_message_id": None,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return ItineraryVersionDraft(**payload)


def test_draft_carries_no_identity_or_version_number():
    draft = _draft()

    assert not hasattr(draft, "itinerary_version_id")
    assert not hasattr(draft, "version_number")
    assert draft.workspace_id == "tw_planner"
    assert draft.created_at == MOMENT
    with pytest.raises(PlannerValidationError):
        _draft(workspace_id="   ")
    with pytest.raises(PlannerValidationError):
        _draft(status="flying")


def test_generated_ids_use_governed_prefixes():
    assert generate_itinerary_version_id().startswith("itv_")
    assert generate_decision_id().startswith("td_")
    assert generate_operation_id().startswith("po_")
    assert len({generate_itinerary_version_id() for _ in range(10)}) == 10


def test_required_text_is_stripped_and_validated():
    item = _item(title="  Bún chả  ")
    assert item.title == "Bún chả"
    with pytest.raises(PlannerValidationError):
        _item(title="   ")
    with pytest.raises(PlannerValidationError):
        _item(title="x" * 121)


def test_optional_blank_text_becomes_none():
    assert _item(location="   ").location is None
    assert _item(notes="").notes is None
    assert _version(title="  ").title is None
    assert _decision(rationale="  ").rationale is None
    assert _operation(input_summary="").input_summary is None


def test_version_day_and_position_values_are_positive():
    assert _version(version_number=2).version_number == 2
    with pytest.raises(PlannerValidationError):
        _version(version_number=0)
    with pytest.raises(PlannerValidationError):
        _item(day_index=0)
    with pytest.raises(PlannerValidationError):
        _item(position=-1)
    with pytest.raises(PlannerValidationError):
        _item(day_index=True)


def test_datetimes_must_be_timezone_aware_utc():
    assert _version().created_at.tzinfo is not None
    with pytest.raises(PlannerValidationError):
        _version(created_at=datetime(2026, 9, 5, 12, 0, 0))
    with pytest.raises(PlannerValidationError):
        _decision(created_at="2026-09-05T12:00:00+00:00")


def test_itinerary_items_are_typed():
    assert _item(item_type="meal").item_type is ItineraryItemType.MEAL
    with pytest.raises(PlannerValidationError):
        _item(item_type="teleport")


def test_decision_updated_at_is_not_earlier_than_created_at():
    assert _decision(updated_at=MOMENT + timedelta(seconds=1)).updated_at > MOMENT
    with pytest.raises(PlannerValidationError):
        _decision(updated_at=MOMENT - timedelta(seconds=1))


def test_status_fields_reject_unknown_values():
    with pytest.raises(PlannerValidationError):
        _version(status="flying")
    with pytest.raises(PlannerValidationError):
        _decision(status="maybe")
    with pytest.raises(PlannerValidationError):
        _decision(decision_type="vibes")
    with pytest.raises(PlannerValidationError):
        _operation(operation_type="time_travel")
    with pytest.raises(PlannerValidationError):
        _operation(status="pending")


def test_governed_planner_vocabularies():
    assert {item.value for item in ItineraryStatus} == {
        "draft",
        "proposed",
        "accepted",
        "superseded",
        "archived",
    }
    assert {item.value for item in ItineraryItemType} == {
        "activity",
        "lodging",
        "transport",
        "meal",
        "free_time",
        "note",
    }
    assert {item.value for item in DecisionType} == {
        "preference",
        "constraint",
        "booking",
        "rejection",
        "tradeoff",
        "open_question",
    }
    assert {item.value for item in DecisionStatus} == {
        "pending",
        "accepted",
        "rejected",
        "changed",
        "superseded",
    }
    assert {item.value for item in PlannerOperationType} == {
        "create_itinerary",
        "accept_itinerary",
        "archive_itinerary",
        "record_decision",
        "update_decision_status",
        "supersede_decision",
    }
    assert {item.value for item in PlannerOperationStatus} == {"applied"}


def test_source_decision_ids_hold_governed_prefixes():
    item = _item(source_decision_ids=[generate_decision_id()])
    assert item.source_decision_ids[0].startswith("td_")
    with pytest.raises(PlannerValidationError):
        _item(source_decision_ids=["mc_not_a_decision"])
