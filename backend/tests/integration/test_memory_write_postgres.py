"""Integration tests for the PostgreSQL memory unit of work.

Every test runs against the ISOLATED disposable PostgreSQL addressed by
`PG_TEST_DSN` (dedicated container and database, never user data). When
the variable is unset the module skips distinctly instead of
pretending to be green. Changesets come from the real Child-2
resolver/policy; persistence shape, ownership, idempotency,
staleness, concurrency, and per-stage failure atomicity are proven
against live rows.
"""

import threading
from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from backend.tests.integration.pg_dsn import migration_dsn, require

MOMENT = datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc)
NEWER = datetime(2026, 9, 7, 13, 0, 0, tzinfo=timezone.utc)

requires_pg = pytest.mark.skipif(
    not migration_dsn(),
    reason="isolated PG unavailable: set PG_TEST_DSN to a disposable database",
)
pytestmark = requires_pg

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
    """The DDL-capable DSN: this module drops and rebuilds the schema."""
    return require(migration_dsn(), "PG_TEST_DSN")


@pytest.fixture(scope="module")
def pg_engine():
    from backend.storage.postgres import create_engine

    engine = create_engine(_test_dsn())
    try:
        with engine.connect() as connection:
            connection.execute(sa.text("SELECT 1"))
    except Exception as error:
        engine.dispose()
        raise RuntimeError(
            f"isolated PG unreachable: {type(error).__name__}; "
            "a configured PG_TEST_DSN must be reachable, not skipped."
        ) from error
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


def _apply(
    uow,
    change,
    candidate,
    owner="owner_a",
    key="key-default",
    expected=None,
    fence=None,
):
    return uow.apply_memory_change(
        change,
        _principal(owner),
        evidence=(_evidence(owner_user_id=candidate.owner_user_id),),
        decision=_decided(candidate),
        idempotency_key=key,
        expected_version_id=expected,
        fence=fence,
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
        # ADR 0031: the key is reserved before the effect and filled after it.
        # A failure at either stage must leave zero rows, which is exactly what
        # sharing one transaction buys.
        "_reserve_idempotency",
        "_fill_idempotency",
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


# 5. Fencing: a delete landing between extraction and commit writes nothing.


def test_fenced_write_rejected_after_conversation_delete(uow, clean):
    """End-to-end proof that delete propagation fences a stale worker write.

    A worker extracts against epoch 0 and a live lease, the conversation is
    then deleted (tombstone + outbox cancel + evidence invalidate + epoch
    bump in one transaction), and the subsequent memory commit with the
    stale fence raises instead of writing.
    """
    import pytest as _pytest

    from backend.conversations.models import MessageRole, MessageSource
    from backend.conversations.postgres_repository import (
        PostgresConversationRepository,
    )
    from backend.conversations.service import ConversationService
    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.uow import FenceContext, FencedWriteError

    repo = PostgresConversationRepository(clean)
    service = ConversationService(conversation_repository=repo)
    conv = service.create_conversation(owner_user_id="owner_a", title="Fence proof")
    service.append_message(
        conv.conversation_id,
        MessageRole.USER,
        "quiet please",
        "owner_a",
        source=MessageSource.UI,
        outbox_event={
            "event_type": "memory.extract.conversation_range",
            "payload": {"conversation_id": conv.conversation_id},
        },
    )
    with clean.connect() as connection:
        outbox_id = connection.execute(
            sa.text(
                "SELECT outbox_id FROM conversation_outbox WHERE conversation_id = :c"
            ),
            {"c": conv.conversation_id},
        ).scalar()
        assert outbox_id is not None
        # Simulate the worker's lease claim.
        connection.execute(
            sa.text(
                "UPDATE conversation_outbox SET status = 'leased', "
                "lease_owner = 'worker_1' WHERE outbox_id = :o"
            ),
            {"o": outbox_id},
        )
        connection.commit()

    fence = FenceContext(
        conversation_id=conv.conversation_id,
        expected_epoch=0,
        outbox_id=outbox_id,
        lease_owner="worker_1",
    )
    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    result = uow.apply_memory_change(
        change,
        _principal("owner_a"),
        evidence=(_evidence(conversation_id=conv.conversation_id),),
        decision=_decided(candidate),
        idempotency_key="key-fence-first",
        fence=fence,
    )
    assert result.version_id is not None

    # The delete lands after extraction.
    service.delete_conversation(conv.conversation_id, "owner_a")

    with clean.connect() as connection:
        status = connection.execute(
            sa.text("SELECT status FROM conversation_outbox WHERE outbox_id = :o"),
            {"o": outbox_id},
        ).scalar()
        assert status == "cancelled"
        invalidated = connection.execute(
            sa.text(
                "SELECT COUNT(*) FROM memory_evidence "
                "WHERE conversation_id = :c AND invalidated_at IS NOT NULL"
            ),
            {"c": conv.conversation_id},
        ).scalar()
        assert invalidated == 1
        epoch = connection.execute(
            sa.text(
                "SELECT deletion_epoch FROM conversations WHERE conversation_id = :c"
            ),
            {"c": conv.conversation_id},
        ).scalar()
        assert int(epoch) == 1

    # The stale fenced commit writes nothing.
    rival = _candidate(normalized_value="lively", observed_at=NEWER)
    current = _versions(clean, change.identity)
    rival_change = resolve_change(
        rival, current=current, relation=MemoryRelation.CONTRADICTION
    )
    before = _counts(clean)
    with _pytest.raises(FencedWriteError):
        uow.apply_memory_change(
            rival_change,
            _principal("owner_a"),
            evidence=(_evidence(conversation_id=conv.conversation_id),),
            decision=_decided(rival),
            idempotency_key="key-fence-stale",
            fence=fence,
        )
    assert _counts(clean) == before


def test_fenced_redelivery_raises_instead_of_cached_success(uow, clean):
    """Fence is verified before the idempotency lookup in the same txn.

    A redelivered write whose fence moved must raise FencedWriteError even
    when its idempotency key already has a stored outcome — returning the
    cached success would report an obsolete event as recorded.
    """
    import pytest as _pytest

    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.memory.write_pipeline.uow import FenceContext, FencedWriteError

    with clean.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO conversations (conversation_id, owner_user_id, "
                "title, retention_state, deletion_epoch, created_at, "
                "updated_at) VALUES ('cv_fence_2', 'owner_a', NULL, 'active', "
                "0, :at, :at)"
            ),
            {"at": MOMENT},
        )
        connection.execute(
            sa.text(
                "INSERT INTO conversation_outbox (outbox_id, conversation_id, "
                "message_id, owner_user_id, event_type, payload, status, "
                "attempt_count, lease_owner, created_at) VALUES ('cout_f2', "
                "'cv_fence_2', 'ms_f2', 'owner_a', "
                "'memory.extract.conversation_range', '{}', 'leased', 1, "
                "'worker_1', :at)"
            ),
            {"at": MOMENT},
        )

    fence = FenceContext(
        conversation_id="cv_fence_2",
        expected_epoch=0,
        outbox_id="cout_f2",
        lease_owner="worker_1",
    )
    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    first = _apply(uow, change, candidate, key="key-fence-order", fence=fence)
    assert first.version_id is not None

    # The source moves: tombstone the conversation (epoch 0 -> 1).
    with clean.begin() as connection:
        connection.execute(
            sa.text(
                "UPDATE conversations SET retention_state = 'tombstoned', "
                "deletion_epoch = 1 WHERE conversation_id = 'cv_fence_2'"
            )
        )

    # Same idempotency key, stale fence: must raise, not replay success.
    rival = _candidate(normalized_value="lively", observed_at=NEWER)
    current = _versions(clean, change.identity)
    rival_change = resolve_change(
        rival, current=current, relation=MemoryRelation.CONTRADICTION
    )
    before = _counts(clean)
    with _pytest.raises(FencedWriteError):
        _apply(uow, rival_change, rival, key="key-fence-order", fence=fence)
    assert _counts(clean) == before


# 12. ADR 0031: the idempotency key enforces its effect.
#
# The key used to be recorded *after* the semantic rows, with the conflict
# swallowed inside a savepoint. The loser of a duplicate-key race therefore
# committed its evidence, decision, version and event rows anyway: one key, two
# semantic effects. Proved with two concurrent transactions before the fix.


def test_a_second_reservation_of_a_held_key_conflicts(clean, uow, pg_engine):
    """The reservation propagates the conflict; it does not swallow it."""
    import time
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy.exc import IntegrityError

    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork
    from backend.memory.write_pipeline.resolver import resolve_change
    from backend.storage.postgres import set_tenant

    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    key = "key-reservation-conflict"
    unit = PostgresMemoryUnitOfWork(pg_engine)

    first = pg_engine.connect()
    transaction = first.begin()
    set_tenant(first, "owner_a")
    unit._reserve_idempotency(first, key, "owner_a", change)

    outcome: dict = {}

    def contend() -> None:
        second = pg_engine.connect()
        competing = second.begin()
        set_tenant(second, "owner_a")
        try:
            unit._reserve_idempotency(second, key, "owner_a", change)
            outcome["result"] = "reserved"
        except IntegrityError as error:
            outcome["result"] = "conflict"
            outcome["pgcode"] = getattr(error.orig, "sqlstate", None)
        finally:
            competing.rollback()
            second.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(contend)
        time.sleep(1.0)  # let the contender block on the uncommitted key
        transaction.commit()  # release it; the contender must now fail
        future.result()
    first.close()

    assert outcome["result"] == "conflict", (
        "a second reservation of a held key must raise, not be swallowed"
    )
    assert outcome["pgcode"] == "23505"


def test_replaying_one_key_commits_one_effect(clean, uow):
    """A replay returns the recorded result and writes nothing new."""
    from backend.memory.write_pipeline.models import MemoryRelation
    from backend.memory.write_pipeline.resolver import resolve_change

    candidate = _candidate()
    change = resolve_change(candidate, current=(), relation=MemoryRelation.UNRELATED)
    key = "key-replay-one-effect"

    first = _apply(uow, change, candidate, key=key)
    before = _counts(clean)
    second = _apply(uow, change, candidate, key=key)
    after = _counts(clean)

    assert second.version_id == first.version_id, "the recorded result is replayed"
    assert after == before, "a replay writes nothing"
    assert after["memory_evidence"] == 1


# The threaded same-key test was removed rather than kept. The mutation proof
# showed it passed whether or not the reservation swallowed its conflict: two
# threads on this fixture usually run one after the other, and the second then
# finds the completed row and replays it. An assertion that cannot fail is
# decoration. `test_a_second_reservation_of_a_held_key_conflicts` is the
# deterministic proof, and it does fail under that mutation.
