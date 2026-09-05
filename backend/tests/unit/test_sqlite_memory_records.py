"""Unit tests for the R6 memory record SQLite store.

Every test uses a `tmp_path` database file, so no test reads or writes the
developer database. The adapter owns the `memory_records` table definitions,
parameterized SQL, and SQLite error handling; the R5 `memory` module version
stays at 1 and no migration framework is introduced.

No test here touches a model provider, Chroma, or the network.
"""

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.memory.models import (
    MemoryPromotionRun,
    MemoryRecord,
    MemoryRecordScope,
    MemoryRecordStatus,
    MemoryRecordType,
    MemorySelectionStatus,
    MemorySelectionTrace,
    PromotionSkipCount,
    PromotionSkipReason,
    SensitivityLabel,
    generate_memory_promotion_run_id,
    generate_memory_record_id,
    generate_memory_retrieval_trace_id,
)
from backend.memory.repository import (
    MemoryAlreadyExistsError,
    MemoryStorageError,
)
from backend.memory.sqlite_repository import (
    SCHEMA_MODULE as CANDIDATE_SCHEMA_MODULE,
)
from backend.memory.sqlite_repository import (
    RECORDS_SCHEMA_MODULE,
    RECORDS_SCHEMA_VERSION,
    SQLiteMemoryRepository,
)

MOMENT = datetime(2026, 9, 5, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "travel_agent.sqlite3"


@pytest.fixture
def repository(db_path: Path) -> SQLiteMemoryRepository:
    return SQLiteMemoryRepository(db_path=db_path)


def _record(**overrides) -> MemoryRecord:
    payload = {
        "memory_id": generate_memory_record_id(),
        "source_candidate_id": "mc_example",
        "workspace_id": "tw_example",
        "conversation_id": "cv_example",
        "source_message_id": "ms_example",
        "source_sequence": 1,
        "owner_user_id": "local-user",
        "scope": MemoryRecordScope.USER,
        "scope_id": "local-user",
        "memory_type": MemoryRecordType.PREFERENCE,
        "status": MemoryRecordStatus.ACTIVE,
        "text": "Người dùng ăn chay trường.",
        "confidence": 0.8,
        "sensitivity_label": SensitivityLabel.NONE,
        "supersedes_memory_id": None,
        "created_at": MOMENT,
        "updated_at": MOMENT,
        "expires_at": None,
    }
    payload.update(overrides)
    return MemoryRecord(**payload)


def _promotion_run(**overrides) -> MemoryPromotionRun:
    payload = {
        "promotion_run_id": generate_memory_promotion_run_id(),
        "workspace_id": "tw_example",
        "conversation_id": "cv_example",
        "source_candidate_count": 1,
        "promoted_count": 1,
        "skipped_count": 0,
        "skip_reasons": (),
        "started_at": MOMENT,
        "finished_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryPromotionRun(**payload)


def _trace(**overrides) -> MemorySelectionTrace:
    payload = {
        "trace_id": generate_memory_retrieval_trace_id(),
        "workspace_id": "tw_example",
        "conversation_id": "cv_example",
        "gate_enabled": True,
        "status": MemorySelectionStatus.SELECTED,
        "selected_ids": (),
        "reasons": (),
        "eligible_count": 0,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return MemorySelectionTrace(**payload)


def _schema_version(db_path: Path, module: str):
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?", (module,)
        ).fetchone()
    return None if row is None else row[0]


# 1. The record store coexists with the R5 candidate store.


def test_initialization_registers_both_memory_modules(
    repository: SQLiteMemoryRepository, db_path: Path
):
    assert _schema_version(db_path, CANDIDATE_SCHEMA_MODULE) == 1
    assert _schema_version(db_path, RECORDS_SCHEMA_MODULE) == 1
    assert RECORDS_SCHEMA_VERSION == 1

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
    assert "memory_records" in tables
    assert "memory_promotion_runs" in tables
    assert "memory_retrieval_events" in tables
    assert "memory_candidates" in tables


def test_record_schema_mismatch_fails_closed(db_path: Path):
    SQLiteMemoryRepository(db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE schema_versions SET version = 999 WHERE module = ?",
            (RECORDS_SCHEMA_MODULE,),
        )
        connection.commit()
    with pytest.raises(MemoryStorageError):
        SQLiteMemoryRepository(db_path=db_path)


def test_candidate_store_still_works_beside_records(
    repository: SQLiteMemoryRepository,
):
    from backend.memory.models import (
        MemoryCandidate,
        MemoryCandidateStatus,
        MemoryExtractionRun,
        MemoryExtractionTrigger,
        MemoryRunStatus,
        MemoryScope,
        MemoryType,
        PolicyReason,
        generate_memory_candidate_id,
        generate_memory_run_id,
    )

    run = MemoryExtractionRun(
        run_id=generate_memory_run_id(),
        workspace_id="tw_example",
        conversation_id="cv_example",
        trigger=MemoryExtractionTrigger.MANUAL,
        extractor_id="rule-based-v1",
        policy_id="policy-v1",
        status=MemoryRunStatus.COMPLETED,
        started_at=MOMENT,
        finished_at=MOMENT,
        candidate_count=1,
        accepted_count=1,
        rejected_count=0,
        needs_user_action_count=0,
        invalid_count=0,
        failure_reason=None,
    )
    repository.create_run(run)
    repository.create_candidates(
        [
            MemoryCandidate(
                candidate_id=generate_memory_candidate_id(),
                run_id=run.run_id,
                workspace_id="tw_example",
                conversation_id="cv_example",
                source_message_id="ms_example",
                source_sequence=1,
                proposed_scope=MemoryScope.USER,
                proposed_type=MemoryType.PREFERENCE,
                status=MemoryCandidateStatus.ACCEPTED,
                confidence=0.8,
                sensitivity_label=SensitivityLabel.NONE,
                text="Người dùng ăn chay trường.",
                evidence_summary="signal=preference:ăn chay",
                reason=PolicyReason.SUPPORTED_PREFERENCE,
                created_at=MOMENT,
            )
        ]
    )
    record = _record()
    repository.create_records([record])
    assert repository.list_records(workspace_id="tw_example") == (record,)
    assert len(repository.list_candidates(workspace_id="tw_example")) == 1


# 2. Record persistence, uniqueness, and scope listing.


def test_create_and_list_records_roundtrip(repository: SQLiteMemoryRepository):
    record = _record()
    assert repository.create_records([record]) == (record,)
    assert repository.list_records(workspace_id="tw_example") == (record,)


def test_duplicate_source_candidate_fails_closed(
    repository: SQLiteMemoryRepository,
):
    repository.create_records([_record(source_candidate_id="mc_dup")])
    with pytest.raises(MemoryAlreadyExistsError):
        repository.create_records([_record(source_candidate_id="mc_dup")])


def test_list_records_applies_scope_and_status_filters(
    repository: SQLiteMemoryRepository,
):
    user_record = _record()
    workspace_record = _record(
        memory_id=generate_memory_record_id(),
        source_candidate_id="mc_two",
        scope=MemoryRecordScope.WORKSPACE,
        scope_id="tw_example",
        memory_type=MemoryRecordType.CONSTRAINT,
        created_at=MOMENT + timedelta(hours=1),
        updated_at=MOMENT + timedelta(hours=1),
    )
    archived = _record(
        memory_id=generate_memory_record_id(),
        source_candidate_id="mc_three",
        status=MemoryRecordStatus.ARCHIVED,
        created_at=MOMENT + timedelta(hours=2),
        updated_at=MOMENT + timedelta(hours=2),
    )
    repository.create_records([user_record, workspace_record, archived])

    assert repository.list_records(owner_user_id="local-user") == (
        user_record,
        workspace_record,
        archived,
    )
    assert repository.list_records(
        workspace_id="tw_example", scope=MemoryRecordScope.WORKSPACE
    ) == (workspace_record,)
    assert repository.list_records(
        workspace_id="tw_example", status=MemoryRecordStatus.ACTIVE
    ) == (user_record, workspace_record)
    assert (
        repository.list_records(
            workspace_id="tw_example",
            conversation_id="cv_other",
        )
        == ()
    )
    assert repository.list_records(workspace_id="tw_other") == ()


def test_mark_records_superseded_flips_active_rows_only(
    repository: SQLiteMemoryRepository,
):
    first = _record()
    second = _record(
        memory_id=generate_memory_record_id(),
        source_candidate_id="mc_two",
    )
    repository.create_records([first, second])
    assert repository.mark_records_superseded([first.memory_id]) == 1
    assert repository.mark_records_superseded([first.memory_id]) == 0
    remaining = repository.list_records(
        workspace_id="tw_example", status=MemoryRecordStatus.ACTIVE
    )
    assert remaining == (second,)
    assert repository.mark_records_superseded(["mem_missing"]) == 0


# 3. Promotion runs and retrieval events.


def test_create_promotion_run_roundtrip_with_skip_reasons(
    repository: SQLiteMemoryRepository, db_path: Path
):
    run = _promotion_run(
        source_candidate_count=3,
        promoted_count=1,
        skipped_count=2,
        skip_reasons=(
            PromotionSkipCount(PromotionSkipReason.NOT_ACCEPTED, 1),
            PromotionSkipCount(PromotionSkipReason.BELOW_MIN_CONFIDENCE, 1),
        ),
    )
    assert repository.create_promotion_run(run) == run
    with sqlite3.connect(db_path) as connection:
        stored = connection.execute(
            "SELECT skip_reasons FROM memory_promotion_runs WHERE promotion_run_id = ?",
            (run.promotion_run_id,),
        ).fetchone()[0]
    assert json.loads(stored) == {
        "below_min_confidence": 1,
        "not_accepted": 1,
    }


def test_list_promotion_runs_returns_newest_first(
    repository: SQLiteMemoryRepository,
):
    first = _promotion_run()
    second = _promotion_run(
        promotion_run_id=generate_memory_promotion_run_id(),
        started_at=MOMENT + timedelta(hours=1),
        finished_at=MOMENT + timedelta(hours=1),
    )
    repository.create_promotion_run(first)
    repository.create_promotion_run(second)
    assert repository.list_promotion_runs(workspace_id="tw_example") == (
        second,
        first,
    )
    assert repository.list_promotion_runs(workspace_id="tw_other") == ()


def test_write_and_list_retrieval_events(repository: SQLiteMemoryRepository):
    first = _trace()
    second = _trace(
        trace_id=generate_memory_retrieval_trace_id(),
        status=MemorySelectionStatus.NONE_SELECTED,
        eligible_count=0,
        created_at=MOMENT + timedelta(hours=1),
    )
    repository.write_retrieval_event(first)
    repository.write_retrieval_event(second)
    assert repository.list_retrieval_events(workspace_id="tw_example") == (
        second,
        first,
    )
    assert (
        repository.list_retrieval_events(
            workspace_id="tw_example", conversation_id="cv_other"
        )
        == ()
    )


# 4. Stored rows outside the contract fail closed.


def test_record_row_outside_contract_fails_closed(
    repository: SQLiteMemoryRepository, db_path: Path
):
    repository.create_records([_record(memory_id="mem_bogus")])
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE memory_records SET status = 'bogus' WHERE memory_id = 'mem_bogus'"
        )
        connection.commit()
    with pytest.raises(MemoryStorageError) as excinfo:
        repository.list_records(workspace_id="tw_example")
    assert "bogus" not in str(excinfo.value)


def test_repository_writes_only_under_the_supplied_path(
    repository: SQLiteMemoryRepository, db_path: Path, tmp_path: Path
):
    assert db_path.is_relative_to(tmp_path)
    repository.create_records([_record()])
    written = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert written == {db_path}
