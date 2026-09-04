"""Unit tests for the R5 memory SQLite repository adapter.

Every test uses a `tmp_path` database file, so no test reads or writes the
developer database. The adapter owns table DDL, parameterized SQL, and
SQLite error handling; routes, service, policy, and extraction code must
never import `sqlite3`.

No test here touches a model provider, Chroma, or the network.
"""

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.memory.models import (
    MemoryCandidate,
    MemoryCandidateStatus,
    MemoryExtractionRun,
    MemoryExtractionTrigger,
    MemoryRunStatus,
    MemoryScope,
    MemoryType,
    PolicyReason,
    SensitivityLabel,
    generate_memory_candidate_id,
    generate_memory_run_id,
)
from backend.memory.repository import (
    MemoryAlreadyExistsError,
    MemoryStorageError,
)
from backend.memory.sqlite_repository import (
    SCHEMA_MODULE,
    SCHEMA_VERSION,
    SQLiteMemoryRepository,
)

MOMENT = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "nested" / "travel_agent.sqlite3"


@pytest.fixture
def repository(db_path: Path) -> SQLiteMemoryRepository:
    return SQLiteMemoryRepository(db_path=db_path)


def _run(**overrides) -> MemoryExtractionRun:
    payload = {
        "run_id": generate_memory_run_id(),
        "workspace_id": "tw_example",
        "conversation_id": "cv_example",
        "trigger": MemoryExtractionTrigger.MANUAL,
        "extractor_id": "rule-based-v1",
        "policy_id": "policy-v1",
        "status": MemoryRunStatus.COMPLETED,
        "started_at": MOMENT,
        "finished_at": MOMENT,
        "candidate_count": 1,
        "accepted_count": 1,
        "rejected_count": 0,
        "needs_user_action_count": 0,
        "invalid_count": 0,
        "failure_reason": None,
    }
    payload.update(overrides)
    return MemoryExtractionRun(**payload)


def _candidate(run_id: str, **overrides) -> MemoryCandidate:
    payload = {
        "candidate_id": generate_memory_candidate_id(),
        "run_id": run_id,
        "workspace_id": "tw_example",
        "conversation_id": "cv_example",
        "source_message_id": "ms_example",
        "source_sequence": 1,
        "proposed_scope": MemoryScope.USER,
        "proposed_type": MemoryType.PREFERENCE,
        "status": MemoryCandidateStatus.ACCEPTED,
        "confidence": 0.8,
        "sensitivity_label": SensitivityLabel.NONE,
        "text": "Người dùng ăn chay trường.",
        "evidence_summary": "ăn chay trường",
        "reason": PolicyReason.SUPPORTED_PREFERENCE,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryCandidate(**payload)


def _schema_objects(db_path: Path, kind: str) -> set[str]:
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ?", (kind,)
        ).fetchall()
    return {row[0] for row in rows}


# 1. Initialization registers the module version and creates the schema.


def test_initialization_registers_the_module_version_and_schema(
    repository: SQLiteMemoryRepository, db_path: Path
):
    with sqlite3.connect(db_path) as connection:
        recorded = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?",
            (SCHEMA_MODULE,),
        ).fetchone()
    assert recorded is not None
    assert recorded[0] == SCHEMA_VERSION == 1

    tables = _schema_objects(db_path, "table")
    assert "memory_extraction_runs" in tables
    assert "memory_candidates" in tables

    indexes = _schema_objects(db_path, "index")
    assert "idx_memory_runs_workspace_order" in indexes
    assert "idx_memory_runs_conversation_order" in indexes
    assert "idx_memory_candidates_run_order" in indexes
    assert "idx_memory_candidates_workspace_filter" in indexes


def test_initialization_is_idempotent(db_path: Path):
    SQLiteMemoryRepository(db_path=db_path)
    SQLiteMemoryRepository(db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        recorded = connection.execute(
            "SELECT version FROM schema_versions WHERE module = ?",
            (SCHEMA_MODULE,),
        ).fetchone()
    assert recorded[0] == 1


def test_schema_mismatch_fails_closed(db_path: Path):
    SQLiteMemoryRepository(db_path=db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE schema_versions SET version = 999 WHERE module = ?",
            (SCHEMA_MODULE,),
        )
        connection.commit()
    with pytest.raises(MemoryStorageError):
        SQLiteMemoryRepository(db_path=db_path)


# 2. Run persistence and newest-first ordering.


def test_create_and_list_runs_roundtrip(repository: SQLiteMemoryRepository):
    run = _run()
    assert repository.create_run(run) == run
    (listed,) = repository.list_runs("tw_example")
    assert listed == run


def test_list_runs_is_newest_first_with_stable_tiebreak(
    repository: SQLiteMemoryRepository,
):
    older = _run(run_id="mer_bbb", started_at=MOMENT)
    newer = _run(run_id="mer_aaa", started_at=MOMENT + timedelta(hours=1))
    tied_old = _run(run_id="mer_ccc", started_at=MOMENT)
    repository.create_run(older)
    repository.create_run(newer)
    repository.create_run(tied_old)
    assert [item.run_id for item in repository.list_runs("tw_example")] == [
        "mer_aaa",
        "mer_bbb",
        "mer_ccc",
    ]


def test_list_runs_filters_by_conversation(repository: SQLiteMemoryRepository):
    repository.create_run(_run(conversation_id="cv_one"))
    other = _run(conversation_id="cv_two")
    repository.create_run(other)
    assert repository.list_runs("tw_example", "cv_two") == (other,)
    assert repository.list_runs("tw_other") == ()


def test_duplicate_run_identity_fails_closed(repository: SQLiteMemoryRepository):
    run = _run(run_id="mer_duplicate")
    repository.create_run(run)
    with pytest.raises(MemoryAlreadyExistsError):
        repository.create_run(run)


# 3. Candidate persistence and governed ordering.


def test_create_candidates_and_list_in_run_order(
    repository: SQLiteMemoryRepository,
):
    run = _run()
    repository.create_run(run)
    second = _candidate(run.run_id, candidate_id="mc_b", source_sequence=2)
    first_b = _candidate(
        run.run_id,
        candidate_id="mc_c",
        source_sequence=1,
        source_message_id="ms_two",
        text="Người dùng thích đi biển.",
        evidence_summary="thích đi biển",
    )
    first_a = _candidate(
        run.run_id,
        candidate_id="mc_a",
        source_sequence=1,
        source_message_id="ms_one",
        text="Người dùng ăn chay.",
        evidence_summary="ăn chay",
    )
    assert repository.create_candidates([second, first_b, first_a]) == (
        second,
        first_b,
        first_a,
    )
    assert repository.list_candidates(run_id=run.run_id) == (
        first_a,
        first_b,
        second,
    )


def test_list_candidates_groups_by_parent_run_newest_first(
    repository: SQLiteMemoryRepository,
):
    old_run = _run(run_id="mer_old", started_at=MOMENT)
    new_run = _run(run_id="mer_new", started_at=MOMENT + timedelta(hours=1))
    repository.create_run(old_run)
    repository.create_run(new_run)
    old_candidate = _candidate(old_run.run_id, source_sequence=1)
    new_candidate = _candidate(new_run.run_id, source_sequence=5)
    repository.create_candidates([old_candidate])
    repository.create_candidates([new_candidate])
    assert repository.list_candidates(workspace_id="tw_example") == (
        new_candidate,
        old_candidate,
    )


def test_list_candidates_applies_workspace_and_conversation_filters(
    repository: SQLiteMemoryRepository,
):
    run = _run()
    repository.create_run(run)
    candidate = _candidate(run.run_id)
    repository.create_candidates([candidate])
    assert repository.list_candidates(
        workspace_id="tw_example", conversation_id="cv_example"
    ) == (candidate,)
    assert (
        repository.list_candidates(
            workspace_id="tw_example", conversation_id="cv_other"
        )
        == ()
    )
    assert repository.list_candidates(workspace_id="tw_other") == ()


def test_duplicate_candidate_unique_tuple_fails_closed(
    repository: SQLiteMemoryRepository,
):
    run = _run()
    repository.create_run(run)
    repository.create_candidates([_candidate(run.run_id)])
    with pytest.raises(MemoryAlreadyExistsError):
        repository.create_candidates(
            [_candidate(run.run_id, candidate_id=generate_memory_candidate_id())]
        )


def test_candidates_require_an_existing_run(repository: SQLiteMemoryRepository):
    with pytest.raises(MemoryStorageError):
        repository.create_candidates([_candidate("mer_missing")])


def test_create_candidates_empty_is_a_noop(repository: SQLiteMemoryRepository):
    assert repository.create_candidates([]) == ()


# 4. Stored rows outside the contract fail closed without leaking content.


def test_run_row_outside_contract_fails_closed(
    repository: SQLiteMemoryRepository, db_path: Path
):
    repository.create_run(_run(run_id="mer_bogus"))
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE memory_extraction_runs SET status = 'bogus' "
            "WHERE run_id = 'mer_bogus'"
        )
        connection.commit()
    with pytest.raises(MemoryStorageError) as excinfo:
        repository.list_runs("tw_example")
    assert "bogus" not in str(excinfo.value)


def test_candidate_row_outside_contract_fails_closed(
    repository: SQLiteMemoryRepository, db_path: Path
):
    run = _run()
    repository.create_run(run)
    repository.create_candidates([_candidate(run.run_id)])
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "UPDATE memory_candidates SET proposed_scope = 'galaxy' WHERE run_id = ?",
            (run.run_id,),
        )
        connection.commit()
    with pytest.raises(MemoryStorageError) as excinfo:
        repository.list_candidates(run_id=run.run_id)
    assert "galaxy" not in str(excinfo.value)


def test_repository_writes_only_under_the_supplied_path(
    repository: SQLiteMemoryRepository, db_path: Path, tmp_path: Path
):
    assert db_path.is_relative_to(tmp_path)
    repository.create_run(_run())
    written = {path for path in tmp_path.rglob("*") if path.is_file()}
    assert written == {db_path}
