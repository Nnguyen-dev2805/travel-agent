"""Integration tests for the PostgreSQL memory unit of work.

Every test runs against the ISOLATED disposable PostgreSQL addressed by
`PG_TEST_DSN` (dedicated container and database, never user data). When
the variable is unset the module skips distinctly instead of
pretending to be green. Changesets come from the real Child-2
resolver/policy; persistence shape, ownership, idempotency,
staleness, concurrency, and per-stage failure atomicity are proven
against live rows.
"""

import os
import threading
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
NEWER = datetime(2026, 9, 7, 13, 0, 0, tzinfo=timezone.utc)

CANONICAL_TABLES = (
    "memory_assertions",
    "memory_versions",
    "memory_evidence",
    "memory_decisions",
    "memory_events",
    "memory_outbox",
    "memory_write_idempotency",
)


def _test_dsn() -> str:
    dsn = os.environ.get("PG_TEST_DSN")
    if not dsn:
        pytest.skip("isolated PG unavailable: set PG_TEST_DSN to a disposable database")
    return dsn


@pytest.fixture(scope="module")
def pg_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(_test_dsn())
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as error:
        engine.dispose()
        pytest.skip(f"isolated PG unreachable: {type(error).__name__}")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated(pg_engine):
    from alembic import command

    from backend.storage.postgres import alembic_config
    from pathlib import Path

    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    with pg_engine.begin() as connection:
        connection.execute(sa.text("DROP SCHEMA public CASCADE"))
        connection.execute(sa.text("CREATE SCHEMA public"))
    command.upgrade(alembic_config(str(migrations), _test_dsn()), "head")
    yield pg_engine


@pytest.fixture()
def clean(pg_engine, migrated):
    with pg_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE memory_write_idempotency, memory_outbox, "
                "memory_events, memory_decisions, memory_evidence, "
                "memory_candidates, memory_versions, memory_assertions"
            )
        )
    yield pg_engine


@pytest.fixture()
def uow(pg_engine):
    from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork

    return PostgresMemoryUnitOfWork(pg_engine)


def _principal(owner="owner_a"):
    from backend.security.models import AuthenticatedPrincipal, AuthMode

    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="test",
    )


def _candidate(**overrides):
    from backend.memory.write_pipeline.models import (
        Authority,
        MemoryCandidate,
        MemoryScope,
        SensitivityBand,
        new_candidate_id,
        new_evidence_id,
    )
    from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY

    payload = {
        "candidate_id": new_candidate_id(),
        "evidence_ids": (new_evidence_id(),),
        "owner_user_id": "owner_a",
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


def _evidence(**overrides):
    from backend.memory.write_pipeline.models import (
        Authority,
        MemoryEvidence,
        new_evidence_id,
    )

    payload = {
        "evidence_id": new_evidence_id(),
        "owner_user_id": "owner_a",
        "conversation_id": "cv_test",
        "source_message_id": "ms_test",
        "display_text": "a quiet hotel",
        "authority": Authority.EXPLICIT_STATEMENT,
        "observed_at": MOMENT,
    }
    payload.update(overrides)
    return MemoryEvidence(**payload)


def _context(**overrides):
    from backend.memory.write_pipeline.policy import (
        Actor,
        DecisionContext,
        Origin,
    )

    payload = {
        "actor": Actor.USER,
        "authenticated": True,
        "origin": Origin.EXPLICIT_COMMAND,
        "source_deleted": False,
        "contextual_sensitivity": None,
    }
    payload.update(overrides)
    return DecisionContext(**payload)


def _decided(candidate, context=None):
    from backend.memory.write_pipeline.policy import decide_candidate

    return decide_candidate(candidate, _context() if context is None else context)


def _apply(uow, change, candidate, owner="owner_a", key="key-default", expected=None):
    return uow.apply_memory_change(
        change,
        _principal(owner),
        evidence=(_evidence(owner_user_id=candidate.owner_user_id),),
        decision=_decided(candidate),
        idempotency_key=key,
        expected_version_id=expected,
    )


def _counts(engine, owner="owner_a") -> dict:
    with engine.connect() as connection:
        return {
            table: connection.execute(
                sa.text(f"SELECT COUNT(*) FROM {table} WHERE owner_user_id = :o"),
                {"o": owner},
            ).scalar()
            for table in CANONICAL_TABLES
        }


def _versions(engine, identity):
    from backend.memory.write_pipeline.postgres import read_current_versions

    return read_current_versions(engine, identity)


# 1. Per-operation persistence shapes.


def test_add_persists_full_shape(uow, clean):
    from backend.memory.write_pipeline.models import MemoryOperation
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.models import MemoryRelation

    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    result = _apply(uow, change, candidate, key="key-add")

    assert result.operation is MemoryOperation.ADD
    assert result.version_id is not None and result.version_id.startswith("mem_")
    assert result.decision_id is not None and result.decision_id.startswith("mdc_")
    assert result.superseded_version_ids == ()
    assert _counts(clean) == {
        "memory_assertions": 1,
        "memory_versions": 1,
        "memory_evidence": 1,
        "memory_decisions": 1,
        "memory_events": 1,
        "memory_outbox": 1,
        "memory_write_idempotency": 1,
    }
    versions = _versions(clean, change.identity)
    assert len(versions) == 1 and versions[0].status.value == "active"


def test_reinforce_writes_no_version(uow, clean):
    from backend.memory.write_pipeline.models import MemoryOperation, MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change

    seed_candidate = _candidate()
    seed = resolve_change(seed_candidate, current=(), relation=MemoryRelation.UNRELATED)
    seed_result = _apply(uow, seed, seed_candidate, key="key-seed")
    current = _versions(clean, seed.identity)
    paraphrase = _candidate(display_text="yên tĩnh nhé")
    change = resolve_change(paraphrase, current=current, relation=MemoryRelation.SAME)
    result = _apply(uow, change, paraphrase, key="key-reinforce")

    assert result.operation is MemoryOperation.REINFORCE
    assert result.version_id is None
    assert result.reference_version_id == seed_result.version_id
    assert len(_versions(clean, seed.identity)) == 1


def test_supersede_flips_exactly_the_active_version(uow, clean):
    from backend.memory.write_pipeline.models import (
        MemoryOperation,
        MemoryRelation,
        VersionStatus,
    )
    from backend.memory.write_pipeline.resolver import resolve_change

    seed_candidate = _candidate()
    seed = resolve_change(seed_candidate, current=(), relation=MemoryRelation.UNRELATED)
    seed_result = _apply(uow, seed, seed_candidate, key="key-seed")
    current = _versions(clean, seed.identity)
    correction = _candidate(normalized_value="lively", observed_at=NEWER)
    change = resolve_change(
        correction, current=current, relation=MemoryRelation.CONTRADICTION
    )
    result = _apply(
        uow,
        change,
        correction,
        key="key-supersede",
        expected=seed_result.version_id,
    )

    assert result.operation is MemoryOperation.SUPERSEDE
    assert result.superseded_version_ids == (seed_result.version_id,)
    versions = {item.version_id: item for item in _versions(clean, seed.identity)}
    assert versions[seed_result.version_id].status is VersionStatus.SUPERSEDED
    assert versions[result.version_id].status is VersionStatus.ACTIVE


def test_exception_keeps_default_active(uow, clean):
    from backend.memory.write_pipeline.models import (
        MemoryOperation,
        MemoryRelation,
        MemoryScope,
        VersionStatus,
        assertion_identity,
    )
    from backend.memory.write_pipeline.resolver import resolve_change

    seed_candidate = _candidate()
    seed = resolve_change(seed_candidate, current=(), relation=MemoryRelation.UNRELATED)
    seed_result = _apply(uow, seed, seed_candidate, key="key-seed")
    current = _versions(clean, seed.identity)
    exception = _candidate(
        scope=MemoryScope.CONVERSATION,
        conversation_id="cv_trip",
        normalized_value="lively",
        observed_at=NEWER,
    )
    change = resolve_change(
        exception, current=current, relation=MemoryRelation.SCOPE_EXCEPTION
    )
    result = _apply(uow, change, exception, key="key-exception")

    assert result.operation is MemoryOperation.ADD_EXCEPTION
    versions = _versions(clean, seed.identity) + _versions(
        clean, assertion_identity(exception)
    )
    assert len(versions) == 2
    assert all(item.status is VersionStatus.ACTIVE for item in versions)
    assert result.reference_version_id == seed_result.version_id


def test_pending_writes_no_version(uow, clean):
    from backend.memory.write_pipeline.models import MemoryOperation, MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change

    seed_candidate = _candidate()
    seed = resolve_change(seed_candidate, current=(), relation=MemoryRelation.UNRELATED)
    _apply(uow, seed, seed_candidate, key="key-seed")
    current = _versions(clean, seed.identity)
    rival = _candidate(normalized_value="lively", observed_at=MOMENT)
    change = resolve_change(
        rival, current=current, relation=MemoryRelation.CONTRADICTION
    )
    result = _apply(uow, change, rival, key="key-pending")

    assert result.operation is MemoryOperation.PENDING_CONFLICT
    assert result.version_id is None
    assert len(_versions(clean, seed.identity)) == 1
    assert _counts(clean)["memory_decisions"] >= 1
    assert _counts(clean)["memory_outbox"] >= 1


def test_reject_persists_nothing(uow, clean):
    from backend.memory.write_pipeline.models import (
        MemoryOperation,
        MemoryRelation,
        SensitivityBand,
    )
    from backend.memory.write_pipeline.resolver import resolve_change

    exposed = _candidate(sensitivity=SensitivityBand.PROHIBITED_SECRET)
    change = resolve_change(
        exposed,
        current=(),
        relation=MemoryRelation.CONTRADICTION,
    )
    result = _apply(uow, change, exposed, key="key-reject")

    assert result.operation is MemoryOperation.REJECT
    assert all(count == 0 for count in _counts(clean).values())


def test_unknown_key_reject_persists_nothing(uow, clean):
    from backend.memory.write_pipeline.models import MemoryOperation, MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change

    foreign = _candidate(canonical_key="travel.preference.unknown_key")
    change = resolve_change(
        foreign,
        current=(),
        relation=MemoryRelation.UNRELATED,
    )
    result = _apply(uow, change, foreign, key="key-unknown")

    assert result.operation is MemoryOperation.REJECT
    assert all(count == 0 for count in _counts(clean).values())


def test_noop_persists_nothing(uow, clean):
    from backend.memory.write_pipeline.models import (
        Authority,
        MemoryOperation,
        MemoryRelation,
    )
    from backend.memory.write_pipeline.resolver import resolve_change

    seed_candidate = _candidate()
    seed = resolve_change(seed_candidate, current=(), relation=MemoryRelation.UNRELATED)
    _apply(uow, seed, seed_candidate, key="key-seed")
    current = _versions(clean, seed.identity)
    weak = _candidate(
        normalized_value="lively",
        authority=Authority.REPEATED_INFERENCE,
        observed_at=NEWER,
    )
    change = resolve_change(
        weak, current=current, relation=MemoryRelation.CONTRADICTION
    )
    before = _counts(clean)
    result = _apply(uow, change, weak, key="key-noop")

    assert result.operation is MemoryOperation.NOOP
    assert _counts(clean) == before


# 2. Tenant, ownership, idempotency, staleness.


def test_missing_tenant_context_fails_closed(clean):
    from backend.storage.postgres import (
        TenantContextError,
        require_tenant_context,
        transaction,
    )

    with transaction(clean) as connection:
        with pytest.raises(TenantContextError):
            require_tenant_context(connection)


def test_cross_owner_apply_is_denied_without_writes(uow, clean):
    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.uow import CrossOwnerDeniedError

    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    with pytest.raises(CrossOwnerDeniedError):
        _apply(uow, change, candidate, owner="owner_b", key="key-xowner")
    assert all(count == 0 for count in _counts(clean).values())


def test_duplicate_idempotency_key_returns_prior_result(uow, clean):
    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change

    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    first = _apply(uow, change, candidate, key="key-dedupe")
    before = _counts(clean)
    second = _apply(uow, change, candidate, key="key-dedupe")

    assert second == first
    assert _counts(clean) == before


def test_stale_expected_version_is_rejected(uow, clean):
    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.uow import StaleVersionError

    seed_candidate = _candidate()
    seed = resolve_change(seed_candidate, current=(), relation=MemoryRelation.UNRELATED)
    _apply(uow, seed, seed_candidate, key="key-seed")
    current = _versions(clean, seed.identity)
    correction = _candidate(normalized_value="lively", observed_at=NEWER)
    change = resolve_change(
        correction, current=current, relation=MemoryRelation.CONTRADICTION
    )
    with pytest.raises(StaleVersionError):
        _apply(uow, change, correction, key="key-stale", expected="mem_wrong_version")
    assert len(_versions(clean, seed.identity)) == 1


# 3. Concurrency: exactly one winner lineage, no duplicate active.


def test_concurrent_writers_yield_one_winner(uow, clean):
    from backend.memory.write_pipeline.models import (
        MemoryRelation,
        assertion_identity,
    )
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.uow import ConcurrentWriteError

    # State isolation: the assertion row pre-exists, so both writers
    # contend ONLY on the version insert behind the assertion row lock.
    # Concurrent first-touch of a missing assertion row is a separate
    # known defect (next test) and is excluded from this window.
    identity = assertion_identity(_candidate())
    with clean.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO memory_assertions "
                "(assertion_id, owner_user_id, scope, scope_id, canonical_key, "
                "subject_key, condition_fingerprint, created_at, updated_at) "
                "VALUES ('mas_race_parent', :o, :s, :sid, :k, :subj, :fp, :at, :at)"
            ),
            {
                "o": identity.owner_user_id,
                "s": identity.scope.value,
                "sid": identity.scope_id,
                "k": identity.canonical_key,
                "subj": identity.subject_key,
                "fp": identity.condition_fingerprint,
                "at": MOMENT,
            },
        )

    barrier = threading.Barrier(3)
    outcomes = []

    def attempt(suffix):
        from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork

        worker = PostgresMemoryUnitOfWork(clean)
        change = resolve_change(
            _candidate(), current=(), relation=MemoryRelation.UNRELATED
        )
        barrier.wait()
        try:
            outcomes.append(
                (
                    "ok",
                    worker.apply_memory_change(
                        change, _principal(), idempotency_key=f"key-race-{suffix}"
                    ),
                )
            )
        except Exception as error:  # surfaced below; never swallowed
            outcomes.append(("error", error))

    threads = [
        threading.Thread(target=attempt, args=(suffix,)) for suffix in ("a", "b")
    ]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join()

    assert len(outcomes) == 2
    assert sum(1 for kind, _ in outcomes if kind == "ok") == 1
    conflicts = [error for kind, error in outcomes if kind == "error"]
    assert len(conflicts) == 1
    assert isinstance(conflicts[0], ConcurrentWriteError), conflicts[0]
    with clean.connect() as connection:
        active = connection.execute(
            sa.text("SELECT COUNT(*) FROM memory_versions WHERE status = 'active'")
        ).scalar()
    assert active == 1


def test_concurrent_first_touch_yields_one_winner(uow, clean):
    import time

    from backend.memory.write_pipeline.models import MemoryRelation, assertion_identity
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork
    from backend.memory.write_pipeline.uow import MemoryWriteError

    identity = assertion_identity(_candidate())
    holder = clean.connect()
    holder_txn = holder.begin()
    try:
        holder.execute(
            sa.text(
                "INSERT INTO memory_assertions "
                "(assertion_id, owner_user_id, scope, scope_id, canonical_key, "
                "subject_key, condition_fingerprint, created_at, updated_at) "
                "VALUES ('mas_race_first', :o, :s, :sid, :k, :subj, :fp, :at, :at)"
            ),
            {
                "o": identity.owner_user_id,
                "s": identity.scope.value,
                "sid": identity.scope_id,
                "k": identity.canonical_key,
                "subj": identity.subject_key,
                "fp": identity.condition_fingerprint,
                "at": MOMENT,
            },
        )
        outcome = {}

        def attempt():
            worker = PostgresMemoryUnitOfWork(clean)
            change = resolve_change(
                _candidate(), current=(), relation=MemoryRelation.UNRELATED
            )
            try:
                outcome["result"] = (
                    "ok",
                    worker.apply_memory_change(
                        change, _principal(), idempotency_key="key-race-first"
                    ),
                )
            except Exception as error:  # surfaced below; never swallowed
                outcome["result"] = ("error", error)

        thread = threading.Thread(target=attempt)
        thread.start()
        # Wait until the worker blocks inside the assertion INSERT behind
        # our held row; only then commit so the race is deterministic.
        deadline = time.monotonic() + 15
        while True:
            with clean.connect() as probe:
                blocked = probe.execute(
                    sa.text(
                        "SELECT COUNT(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() "
                        "AND pid <> pg_backend_pid() "
                        "AND wait_event_type = 'Lock' "
                        "AND query LIKE '%INSERT INTO memory_assertions%'"
                    )
                ).scalar()
            if blocked:
                break
            assert time.monotonic() < deadline, "worker never contended"
            time.sleep(0.05)
        holder_txn.commit()
        thread.join()
    finally:
        if holder_txn.is_active:
            holder_txn.rollback()
        holder.close()

    kind, payload = outcome["result"]
    # Post-fix there is no loser: the worker retries past the lost
    # assertion race and wins. A bare MemoryWriteError here (rather
    # than success) is the regressed defect signature, so it must
    # never pass silently: only the designed ConcurrentWriteError
    # taxonomy may ever surface from contention.
    assert kind == "ok", payload
    assert not isinstance(payload, MemoryWriteError), payload
    with clean.connect() as connection:
        active = connection.execute(
            sa.text("SELECT COUNT(*) FROM memory_versions WHERE status = 'active'")
        ).scalar()
    assert active == 1


# 4. Injected failure after each write stage leaves zero partial rows.


@pytest.mark.parametrize(
    "stage",
    [
        "_resolve_assertion",
        "_insert_evidence_rows",
        "_insert_decision_row",
        "_insert_version_row",
        "_mark_versions_superseded",
        "_insert_event_row",
        "_insert_outbox_row",
        "_record_idempotency",
    ],
)
def test_injected_stage_failure_leaves_zero_rows(uow, clean, monkeypatch, stage):
    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change

    def boom(*args, **kwargs):
        raise RuntimeError("injected stage failure")

    monkeypatch.setattr(
        "backend.memory.write_pipeline.postgres.PostgresMemoryUnitOfWork." + stage,
        boom,
    )
    # The supersession stage is reachable only on a SUPERSEDE change, so
    # that case seeds a live version first; every other stage runs on a
    # fresh ADD. Either way the final assertion is the same: the failed
    # apply changes no row counts at all.
    if stage == "_mark_versions_superseded":
        seed_candidate = _candidate()
        seed = resolve_change(
            seed_candidate, current=(), relation=MemoryRelation.UNRELATED
        )
        seed_result = _apply(uow, seed, seed_candidate, key=f"key-fault-{stage}-seed")
        current = _versions(clean, seed.identity)
        candidate = _candidate(normalized_value="lively", observed_at=NEWER)
        change = resolve_change(
            candidate, current=current, relation=MemoryRelation.CONTRADICTION
        )
        extra = {"expected": seed_result.version_id}
    else:
        candidate = _candidate()
        change = resolve_change(
            candidate, current=(), relation=MemoryRelation.UNRELATED
        )
        extra = {}
    before = _counts(clean)
    with pytest.raises(RuntimeError, match="injected stage failure"):
        _apply(uow, change, candidate, key=f"key-fault-{stage}", **extra)

    assert _counts(clean) == before
