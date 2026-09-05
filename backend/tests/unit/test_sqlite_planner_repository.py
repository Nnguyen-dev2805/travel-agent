"""Unit tests for the R7 planner SQLite repository.

Every test runs against an isolated temporary database path, so no test
reads or writes the developer database at `APP_DB_PATH`. No test touches a
model provider, RAG retrieval, Chroma, memory, orchestration, or the network.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from backend.planner.models import (
    DecisionStatus,
    DecisionType,
    ItineraryItem,
    ItineraryItemType,
    ItineraryStatus,
    ItineraryVersionDraft,
    PlannerOperation,
    PlannerOperationStatus,
    PlannerOperationType,
    TripDecision,
    generate_decision_id,
    generate_itinerary_version_id,
    generate_operation_id,
)
from backend.planner.repository import (
    PlannerNotFoundError,
    PlannerRepositoryError,
    PlannerStorageError,
)
from backend.planner.sqlite_repository import (
    PLANNER_SCHEMA_MODULE,
    PLANNER_SCHEMA_VERSION,
    SQLitePlannerRepository,
)
from backend.storage.schema_registry import (
    open_application_database,
    read_module_version,
    register_module_schema,
)

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


def _repo(tmp_path: Path) -> SQLitePlannerRepository:
    return SQLitePlannerRepository(db_path=tmp_path / "planner.sqlite3")


def _item(**overrides) -> ItineraryItem:
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


def _decision(**overrides) -> TripDecision:
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


def _operation(**overrides) -> PlannerOperation:
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


def test_schema_registers_planner_state_version_1(tmp_path: Path):
    db_path = tmp_path / "planner.sqlite3"
    _repo(tmp_path)

    connection = open_application_database(db_path)
    try:
        assert read_module_version(connection, PLANNER_SCHEMA_MODULE) == 1
    finally:
        connection.close()
    assert PLANNER_SCHEMA_VERSION == 1


def test_schema_initialization_is_idempotent(tmp_path: Path):
    first = _repo(tmp_path)
    first.create_itinerary_version(_draft(), generate_itinerary_version_id())

    second = _repo(tmp_path)

    assert len(second.list_itinerary_versions("tw_planner")) == 1


def test_schema_mismatch_fails_closed(tmp_path: Path):
    db_path = tmp_path / "planner.sqlite3"
    connection = open_application_database(db_path)
    try:
        register_module_schema(connection, PLANNER_SCHEMA_MODULE, 99, lambda _: None)
    finally:
        connection.close()

    with pytest.raises(PlannerStorageError):
        _repo(tmp_path)


def test_itinerary_round_trip(tmp_path: Path):
    repo = _repo(tmp_path)
    stored = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())

    fetched = repo.get_itinerary_version("tw_planner", stored.itinerary_version_id)

    assert fetched == stored
    assert fetched.items[0].title == "Bún chả Hương Liên"


def test_version_numbers_are_contiguous_per_workspace(tmp_path: Path):
    repo = _repo(tmp_path)
    first = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    second = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    third = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    other = repo.create_itinerary_version(
        _draft(workspace_id="tw_other"), generate_itinerary_version_id()
    )

    assert (first.version_number, second.version_number, third.version_number) == (
        1,
        2,
        3,
    )
    assert other.version_number == 1


def test_accept_supersedes_prior_accepted_in_same_workspace(tmp_path: Path):
    repo = _repo(tmp_path)
    first = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    second = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    other = repo.create_itinerary_version(
        _draft(workspace_id="tw_other"), generate_itinerary_version_id()
    )
    repo.accept_itinerary_version("tw_planner", first.itinerary_version_id)
    repo.accept_itinerary_version("tw_other", other.itinerary_version_id)

    accepted = repo.accept_itinerary_version("tw_planner", second.itinerary_version_id)

    assert accepted.status is ItineraryStatus.ACCEPTED
    assert (
        repo.get_itinerary_version("tw_planner", first.itinerary_version_id).status
        is ItineraryStatus.SUPERSEDED
    )
    assert (
        repo.get_itinerary_version("tw_other", other.itinerary_version_id).status
        is ItineraryStatus.ACCEPTED
    )


def test_accept_is_idempotent_for_already_accepted(tmp_path: Path):
    repo = _repo(tmp_path)
    stored = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    repo.accept_itinerary_version("tw_planner", stored.itinerary_version_id)

    again = repo.accept_itinerary_version("tw_planner", stored.itinerary_version_id)

    assert again.status is ItineraryStatus.ACCEPTED


def test_status_update_round_trip(tmp_path: Path):
    repo = _repo(tmp_path)
    stored = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())

    archived = repo.update_itinerary_status(
        "tw_planner", stored.itinerary_version_id, ItineraryStatus.ARCHIVED
    )

    assert archived.status is ItineraryStatus.ARCHIVED
    assert (
        repo.get_itinerary_version("tw_planner", stored.itinerary_version_id).status
        is ItineraryStatus.ARCHIVED
    )


def test_list_versions_is_newest_first_and_scoped(tmp_path: Path):
    repo = _repo(tmp_path)
    first = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    second = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    repo.create_itinerary_version(
        _draft(workspace_id="tw_other"), generate_itinerary_version_id()
    )

    listed = repo.list_itinerary_versions("tw_planner")

    assert [item.itinerary_version_id for item in listed] == [
        second.itinerary_version_id,
        first.itinerary_version_id,
    ]


def test_decision_round_trip_with_rejected_status(tmp_path: Path):
    repo = _repo(tmp_path)
    stored = repo.create_decision(_decision(status=DecisionStatus.REJECTED))

    fetched = repo.get_decision("tw_planner", stored.decision_id)
    listed = repo.list_decisions("tw_planner", status=DecisionStatus.REJECTED)

    assert fetched == stored
    assert [item.decision_id for item in listed] == [stored.decision_id]


def test_replacement_decision_supersedes_same_workspace_target(tmp_path: Path):
    repo = _repo(tmp_path)
    old = repo.create_decision(_decision(status=DecisionStatus.ACCEPTED))
    replacement = repo.create_decision(
        _decision(
            status=DecisionStatus.ACCEPTED,
            supersedes_decision_id=old.decision_id,
        )
    )

    assert (
        repo.get_decision("tw_planner", old.decision_id).status
        is DecisionStatus.SUPERSEDED
    )
    assert replacement.supersedes_decision_id == old.decision_id


def test_replacement_decision_rejects_cross_workspace_target(tmp_path: Path):
    repo = _repo(tmp_path)
    old = repo.create_decision(
        _decision(workspace_id="tw_other", status=DecisionStatus.ACCEPTED)
    )

    with pytest.raises(PlannerNotFoundError):
        repo.create_decision(_decision(supersedes_decision_id=old.decision_id))


def test_cross_workspace_ids_are_not_found(tmp_path: Path):
    repo = _repo(tmp_path)
    stored = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    decision = repo.create_decision(_decision())

    with pytest.raises(PlannerNotFoundError):
        repo.get_itinerary_version("tw_other", stored.itinerary_version_id)
    with pytest.raises(PlannerNotFoundError):
        repo.accept_itinerary_version("tw_other", stored.itinerary_version_id)
    with pytest.raises(PlannerNotFoundError):
        repo.get_decision("tw_other", decision.decision_id)
    assert repo.list_itinerary_versions("tw_other") == ()
    assert repo.list_decisions("tw_other") == ()


def test_operation_rows_list_newest_first(tmp_path: Path):
    repo = _repo(tmp_path)
    first = repo.create_operation(_operation())
    second = repo.create_operation(_operation())
    repo.create_operation(_operation(workspace_id="tw_other"))

    listed = repo.list_operations("tw_planner")

    assert [item.operation_id for item in listed] == [
        second.operation_id,
        first.operation_id,
    ]


def test_repository_errors_share_a_common_base():
    assert issubclass(PlannerNotFoundError, PlannerRepositoryError)
    assert issubclass(PlannerStorageError, PlannerRepositoryError)


def _draft(**overrides):
    payload = {
        "workspace_id": "tw_planner",
        "status": ItineraryStatus.DRAFT,
        "title": "Hà Nội 3 ngày",
        "summary": None,
        "items": (_item(),),
        "created_from_operation_id": None,
        "created_from_message_id": None,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return ItineraryVersionDraft(**payload)


def _create_operation(**overrides):
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


def test_failed_operation_rolls_back_itinerary_create(tmp_path: Path):
    # The operation row shares the state-change transaction: when the
    # operation insert fails, the itinerary version must not survive, and
    # the version sequence must stay unpolluted.
    repo = _repo(tmp_path)
    repo.create_operation(_create_operation(operation_id="po_taken"))

    with pytest.raises(PlannerStorageError):
        repo.create_itinerary_version(
            _draft(),
            generate_itinerary_version_id(),
            operation=_create_operation(operation_id="po_taken"),
        )

    assert repo.list_itinerary_versions("tw_planner") == ()
    assert repo.list_operations("tw_planner")[0].operation_id == "po_taken"
    retry = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    assert retry.version_number == 1


def test_failed_operation_rolls_back_accept_flip(tmp_path: Path):
    repo = _repo(tmp_path)
    first = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    second = repo.create_itinerary_version(_draft(), generate_itinerary_version_id())
    repo.accept_itinerary_version(
        "tw_planner",
        first.itinerary_version_id,
        operation=_create_operation(
            operation_type=PlannerOperationType.ACCEPT_ITINERARY
        ),
    )
    repo.create_operation(_create_operation(operation_id="po_taken"))

    with pytest.raises(PlannerStorageError):
        repo.accept_itinerary_version(
            "tw_planner",
            second.itinerary_version_id,
            operation=_create_operation(
                operation_id="po_taken",
                operation_type=PlannerOperationType.ACCEPT_ITINERARY,
            ),
        )

    assert (
        repo.get_itinerary_version("tw_planner", first.itinerary_version_id).status
        is ItineraryStatus.ACCEPTED
    )
    assert (
        repo.get_itinerary_version("tw_planner", second.itinerary_version_id).status
        is ItineraryStatus.DRAFT
    )
