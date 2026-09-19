"""Integration tests for PostgresMemoryStore and MemoryReadEngine with live PostgreSQL.

Covers:
- PENDING_CONFLICT sets memory_assertions.has_unresolved_conflict = TRUE atomically
- Explicit authoritative resolution (ADD/REINFORCE/SUPERSEDE/REVOKE) clears it atomically
- NOOP / PENDING_CONFLICT does not clear it
- Rollback preserves prior flag
- PostgresMemoryStore projects stamped vs current generation, conflict flag, typed enums, and tuple set values
- RLS enforces owner isolation
- MemoryReadEngine end-to-end: whole-key conflict suppression, conversation override without mutation, unrelated key abstention
"""

from datetime import datetime, timezone
from pathlib import Path
import pytest
import sqlalchemy as sa

from backend.memory.lifecycle import SourceValidity
from backend.memory.postgres_store import PostgresMemoryStore
from backend.memory.read_engine import MemoryReadEngine
from backend.memory.read_models import AbstentionReason, MemoryReadRequest
from backend.memory.write_pipeline.models import (
    AssertionIdentity,
    Authority,
    MemoryChangeSet,
    MemoryEvidence,
    MemoryOperation,
    MemoryScope,
    MemoryVersionDraft,
    NormalizedSemanticValue,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
    new_candidate_id,
    new_evidence_id,
)
from backend.memory.write_pipeline.postgres import (
    PostgresMemoryUnitOfWork,
    assertions_table,
    versions_table,
)
from backend.security.models import AuthenticatedPrincipal, AuthMode
from backend.storage.postgres import create_engine, set_tenant
from backend.tests.integration.pg_dsn import (
    migration_dsn,
    require,
    runtime_dsn,
)

HOTEL_ATMOSPHERE_KEY = "travel.preference.hotel_atmosphere"
TRANSPORT_MODE_KEY = "travel.preference.transport_mode"
TRAVEL_PACE_KEY = "travel.preference.travel_pace"

requires_pg = pytest.mark.skipif(
    not runtime_dsn(),
    reason="isolated PG unavailable: set PG_RUNTIME_TEST_DSN to a disposable database",
)
pytestmark = requires_pg

NOW = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def ddl_engine():
    engine = create_engine(require(migration_dsn(), "PG_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def runtime_engine():
    engine = create_engine(require(runtime_dsn(), "PG_RUNTIME_TEST_DSN"))
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def migrated(ddl_engine):
    from alembic import command
    from backend.storage.postgres import alembic_config

    migrations = (
        Path(__file__).resolve().parent.parent.parent / "storage" / "migrations"
    )
    command.upgrade(
        alembic_config(str(migrations), require(migration_dsn(), "PG_TEST_DSN")),
        "head",
    )
    yield ddl_engine


@pytest.fixture()
def clean(ddl_engine, migrated):
    with ddl_engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE memory_write_idempotency, memory_outbox, "
                "memory_events, memory_decisions, memory_evidence, "
                "memory_candidates, memory_versions, memory_assertions, "
                "messages, conversations CASCADE"
            )
        )
    yield ddl_engine


def _principal(owner: str = "owner_a"):
    return AuthenticatedPrincipal(
        owner_user_id=owner,
        auth_mode=AuthMode.AUTHENTICATED,
        credential_label="test",
    )


def _evidence(owner: str, conversation_id: str = "cv_1"):
    return (
        MemoryEvidence(
            evidence_id=new_evidence_id(),
            owner_user_id=owner,
            conversation_id=conversation_id,
            source_message_id="msg_1",
            display_text="I want quiet hotels",
            authority=Authority.EXPLICIT_SAVE,
            observed_at=NOW,
        ),
    )


def _identity(
    owner: str,
    key: str = HOTEL_ATMOSPHERE_KEY,
    scope: MemoryScope = MemoryScope.USER,
    scope_id: str | None = None,
):
    return AssertionIdentity(
        owner_user_id=owner,
        canonical_key=key,
        scope=scope,
        scope_id=scope_id or owner,
        subject_key="subject_default",
        condition_fingerprint="cond_default",
    )


def _draft(
    owner: str,
    key: str = HOTEL_ATMOSPHERE_KEY,
    value: NormalizedSemanticValue = "quiet",
    scope: MemoryScope = MemoryScope.USER,
    scope_id: str | None = None,
    retention_mode: RetentionMode = RetentionMode.USER_DURABLE,
    authority: Authority = Authority.EXPLICIT_SAVE,
    supersedes_version_id: str | None = None,
) -> MemoryVersionDraft:
    return MemoryVersionDraft(
        owner_user_id=owner,
        scope=scope,
        scope_id=scope_id or owner,
        canonical_key=key,
        subject_key="subject_default",
        condition_fingerprint="cond_default",
        normalized_value=value,
        display_text=f"display {value}",
        authority=authority,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        retention_mode=retention_mode,
        valid_from=NOW,
        supersedes_version_id=supersedes_version_id,
    )


def _apply(
    uow: PostgresMemoryUnitOfWork,
    owner: str,
    operation: MemoryOperation,
    identity: AssertionIdentity,
    new_version: MemoryVersionDraft | None = None,
    superseded_version_ids: tuple[str, ...] = (),
    reference_version_id: str | None = None,
    reason: str = "test",
    evidence: tuple[MemoryEvidence, ...] | None = None,
    idempotency_key: str | None = None,
):
    change = MemoryChangeSet(
        operation=operation,
        identity=identity,
        new_version=new_version,
        superseded_version_ids=superseded_version_ids,
        reference_version_id=reference_version_id,
        reason=reason,
    )
    if new_version is not None:
        source_validity = (
            SourceValidity.NOT_REQUIRED
            if new_version.retention_mode is RetentionMode.USER_DURABLE
            else SourceValidity.VALID
        )
    else:
        source_validity = None

    return uow.apply_memory_change(
        change,
        _principal(owner),
        evidence=_evidence(owner) if evidence is None else evidence,
        idempotency_key=idempotency_key,
        source_validity=source_validity,
    )


# --- Conflict Flag Integration Tests ---


def test_pending_conflict_sets_flag_atomically(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    owner = "owner_conflict_1"
    ident = _identity(owner)

    # 1. ADD initial version
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        ident,
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_add_1",
    )

    # Verify initial has_unresolved_conflict is False
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        row = (
            conn.execute(
                sa.select(
                    assertions_table.c.has_unresolved_conflict,
                    assertions_table.c.assertion_id,
                ).where(
                    assertions_table.c.owner_user_id == owner,
                    assertions_table.c.canonical_key == HOTEL_ATMOSPHERE_KEY,
                )
            )
            .mappings()
            .one()
        )
        assert row["has_unresolved_conflict"] is False
        assertion_id = row["assertion_id"]

    # 2. Apply PENDING_CONFLICT
    _apply(
        uow,
        owner,
        MemoryOperation.PENDING_CONFLICT,
        ident,
        idempotency_key="idemp_conflict_1",
        reason="conflicting preferences detected",
    )

    # Verify has_unresolved_conflict is now True
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        flag = conn.execute(
            sa.select(assertions_table.c.has_unresolved_conflict).where(
                assertions_table.c.assertion_id == assertion_id
            )
        ).scalar_one()
        assert flag is True


def test_explicit_resolution_clears_flag_atomically(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    owner = "owner_conflict_2"
    ident = _identity(owner)

    # 1. ADD
    res_add = _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        ident,
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_add_2",
    )
    active_version_id = res_add.version_id

    # 2. PENDING_CONFLICT
    _apply(
        uow,
        owner,
        MemoryOperation.PENDING_CONFLICT,
        ident,
        idempotency_key="idemp_conflict_2",
        reason="pending conflict",
    )

    # Verify True
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        assert (
            conn.execute(
                sa.select(assertions_table.c.has_unresolved_conflict).where(
                    assertions_table.c.owner_user_id == owner
                )
            ).scalar_one()
            is True
        )

    # 3. Authoritative SUPERSEDE clears conflict flag
    _apply(
        uow,
        owner,
        MemoryOperation.SUPERSEDE,
        ident,
        new_version=_draft(
            owner,
            HOTEL_ATMOSPHERE_KEY,
            "lively",
            supersedes_version_id=active_version_id,
        ),
        superseded_version_ids=(active_version_id,),
        idempotency_key="idemp_supersede_2",
        reason="explicit user correction resolves conflict",
    )

    # Verify cleared to False
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        assert (
            conn.execute(
                sa.select(assertions_table.c.has_unresolved_conflict).where(
                    assertions_table.c.owner_user_id == owner
                )
            ).scalar_one()
            is False
        )


def test_noop_does_not_clear_conflict_flag(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    owner = "owner_conflict_3"
    ident = _identity(owner)

    # ADD
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        ident,
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_add_3",
    )

    # Set conflict flag
    _apply(
        uow,
        owner,
        MemoryOperation.PENDING_CONFLICT,
        ident,
        idempotency_key="idemp_conflict_3",
        reason="conflict",
    )

    # Apply NOOP
    _apply(
        uow,
        owner,
        MemoryOperation.NOOP,
        ident,
        idempotency_key="idemp_noop_3",
        reason="no-op",
    )

    # Flag must STILL be True
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        assert (
            conn.execute(
                sa.select(assertions_table.c.has_unresolved_conflict).where(
                    assertions_table.c.owner_user_id == owner
                )
            ).scalar_one()
            is True
        )


def test_background_write_cannot_clear_flag(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    owner = "owner_conflict_bg"
    ident = _identity(owner)

    # 1. ADD initial version
    res_add = _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        ident,
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_add_bg",
    )
    active_version_id = res_add.version_id

    # 2. PENDING_CONFLICT sets flag to True
    _apply(
        uow,
        owner,
        MemoryOperation.PENDING_CONFLICT,
        ident,
        idempotency_key="idemp_conflict_bg",
        reason="pending conflict",
    )

    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        assert (
            conn.execute(
                sa.select(assertions_table.c.has_unresolved_conflict).where(
                    assertions_table.c.owner_user_id == owner
                )
            ).scalar_one()
            is True
        )

    # 3. Background/inferred REINFORCE with authority=REPEATED_INFERENCE
    change = MemoryChangeSet(
        operation=MemoryOperation.REINFORCE,
        identity=ident,
        new_version=_draft(
            owner,
            HOTEL_ATMOSPHERE_KEY,
            "quiet",
            authority=Authority.REPEATED_INFERENCE,
        ),
        superseded_version_ids=(),
        reference_version_id=active_version_id,
        reason="background reinforcement",
    )
    uow.apply_memory_change(
        change,
        _principal(owner),
        evidence=_evidence(owner),
        idempotency_key="idemp_bg_reinf",
        source_validity=SourceValidity.VALID,
    )

    # Flag must STILL be True!
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        assert (
            conn.execute(
                sa.select(assertions_table.c.has_unresolved_conflict).where(
                    assertions_table.c.owner_user_id == owner
                )
            ).scalar_one()
            is True
        )


def test_rollback_preserves_prior_flag(clean, runtime_engine):
    owner = "owner_rollback"
    ident = _identity(owner)
    uow = PostgresMemoryUnitOfWork(runtime_engine)

    # ADD
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        ident,
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_add_rb",
    )

    # Try applying an invalid change with foreign evidence that causes CrossOwnerDeniedError
    foreign_evidence = (
        MemoryEvidence(
            evidence_id=new_evidence_id(),
            owner_user_id="other_intruder",  # Cross-owner violation!
            conversation_id="cv_1",
            source_message_id="msg_x",
            display_text="conflict",
            authority=Authority.EXPLICIT_SAVE,
            observed_at=NOW,
        ),
    )

    with pytest.raises(Exception):
        _apply(
            uow,
            owner,
            MemoryOperation.PENDING_CONFLICT,
            ident,
            idempotency_key="idemp_fail",
            evidence=foreign_evidence,
            reason="conflict that fails",
        )

    # Prior flag must still be False
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        assert (
            conn.execute(
                sa.select(assertions_table.c.has_unresolved_conflict).where(
                    assertions_table.c.owner_user_id == owner
                )
            ).scalar_one()
            is False
        )


# --- PostgresMemoryStore Physical Projection Tests ---


def test_store_projects_correct_generations_and_tuples(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    owner = "owner_store_1"
    store = PostgresMemoryStore(runtime_engine)

    # 1. Add scalar key
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(owner, HOTEL_ATMOSPHERE_KEY),
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_store_s1",
    )

    # 2. Add set key
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(owner, TRANSPORT_MODE_KEY),
        new_version=_draft(owner, TRANSPORT_MODE_KEY, ("flight", "train")),
        idempotency_key="idemp_store_s2",
    )

    # Read through PostgresMemoryStore
    request = MemoryReadRequest(
        owner_user_id=owner,
        requested_keys=(HOTEL_ATMOSPHERE_KEY, TRANSPORT_MODE_KEY),
    )
    rows = store.list_storage_scoped(request)
    assert len(rows) == 2

    by_key = {r.canonical_key: r for r in rows}
    hotel_row = by_key[HOTEL_ATMOSPHERE_KEY]
    assert hotel_row.normalized_value == "quiet"
    assert hotel_row.scope is MemoryScope.USER
    assert hotel_row.authority is Authority.EXPLICIT_SAVE
    assert hotel_row.retention_mode is RetentionMode.USER_DURABLE
    assert hotel_row.status is VersionStatus.ACTIVE
    assert hotel_row.stamped_generation == 1
    assert hotel_row.current_generation == 1
    assert hotel_row.unresolved_conflict is False
    assert hotel_row.source_validity is SourceValidity.NOT_REQUIRED

    transport_row = by_key[TRANSPORT_MODE_KEY]
    assert isinstance(transport_row.normalized_value, tuple)
    assert transport_row.normalized_value == ("flight", "train")


def test_store_rls_isolates_owner_a_from_owner_b(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    store = PostgresMemoryStore(runtime_engine)

    # Write for owner_a
    _apply(
        uow,
        "owner_alice",
        MemoryOperation.ADD,
        _identity("owner_alice", HOTEL_ATMOSPHERE_KEY),
        new_version=_draft("owner_alice", HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_alice",
        evidence=_evidence("owner_alice"),
    )

    # Query for owner_bob
    request_bob = MemoryReadRequest(
        owner_user_id="owner_bob",
        requested_keys=(HOTEL_ATMOSPHERE_KEY,),
    )
    rows_bob = store.list_storage_scoped(request_bob)
    assert rows_bob == ()

    # Query for owner_alice sees her row
    request_alice = MemoryReadRequest(
        owner_user_id="owner_alice",
        requested_keys=(HOTEL_ATMOSPHERE_KEY,),
    )
    rows_alice = store.list_storage_scoped(request_alice)
    assert len(rows_alice) == 1
    assert rows_alice[0].owner_user_id == "owner_alice"


# --- MemoryReadEngine End-to-End Integration Tests ---


def test_read_engine_whole_key_conflict_suppression_e2e(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    store = PostgresMemoryStore(runtime_engine)
    engine = MemoryReadEngine(store, clock=lambda: NOW)
    owner = "owner_e2e_conflict"

    # Add hotel atmosphere
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(owner, HOTEL_ATMOSPHERE_KEY),
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_e2e_1",
    )

    # Add travel pace
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(owner, TRAVEL_PACE_KEY),
        new_version=_draft(owner, TRAVEL_PACE_KEY, "relaxed"),
        idempotency_key="idemp_e2e_2",
    )

    # Mark conflict on hotel_atmosphere
    _apply(
        uow,
        owner,
        MemoryOperation.PENDING_CONFLICT,
        _identity(owner, HOTEL_ATMOSPHERE_KEY),
        idempotency_key="idemp_e2e_c",
        reason="conflict",
    )

    # Read both keys
    selection = engine.select(
        MemoryReadRequest(
            owner_user_id=owner,
            requested_keys=(HOTEL_ATMOSPHERE_KEY, TRAVEL_PACE_KEY),
        )
    )

    # hotel_atmosphere is suppressed entirely; travel_pace is selected!
    assert len(selection.selected) == 1
    assert selection.selected[0].canonical_key == TRAVEL_PACE_KEY
    assert selection.selected[0].normalized_value == "relaxed"
    assert selection.abstention_reason is None


def test_read_engine_conversation_override_e2e(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    store = PostgresMemoryStore(runtime_engine)
    engine = MemoryReadEngine(store, clock=lambda: NOW)
    owner = "owner_e2e_override"

    # 1. User-scoped preference: quiet
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(
            owner, HOTEL_ATMOSPHERE_KEY, scope=MemoryScope.USER, scope_id=owner
        ),
        new_version=_draft(
            owner,
            HOTEL_ATMOSPHERE_KEY,
            "quiet",
            scope=MemoryScope.USER,
            scope_id=owner,
            retention_mode=RetentionMode.USER_DURABLE,
        ),
        idempotency_key="idemp_user_quiet",
        evidence=_evidence(owner, conversation_id="cv_override"),
    )

    # 2. Conversation-scoped preference: lively in cv_override
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(
            owner,
            HOTEL_ATMOSPHERE_KEY,
            scope=MemoryScope.CONVERSATION,
            scope_id="cv_override",
        ),
        new_version=_draft(
            owner,
            HOTEL_ATMOSPHERE_KEY,
            "lively",
            scope=MemoryScope.CONVERSATION,
            scope_id="cv_override",
            retention_mode=RetentionMode.CONVERSATION_BOUND,
            authority=Authority.EXPLICIT_STATEMENT,
        ),
        idempotency_key="idemp_conv_lively",
        evidence=_evidence(owner, conversation_id="cv_override"),
    )

    # Select in conversation cv_override
    selection = engine.select(
        MemoryReadRequest(
            owner_user_id=owner,
            conversation_id="cv_override",
            requested_keys=(HOTEL_ATMOSPHERE_KEY,),
        )
    )

    assert len(selection.selected) == 1
    selected = selection.selected[0]
    assert selected.scope is MemoryScope.CONVERSATION
    assert selected.scope_id == "cv_override"
    assert selected.normalized_value == "lively"

    # Check that the user-scoped record in the DB was NOT mutated or deleted!
    with runtime_engine.connect() as conn:
        set_tenant(conn, owner)
        user_rows = (
            conn.execute(
                sa.select(
                    versions_table.c.status,
                    versions_table.c.normalized_value,
                )
                .join(
                    assertions_table,
                    versions_table.c.assertion_id
                    == assertions_table.c.assertion_id,
                )
                .where(
                    assertions_table.c.owner_user_id == owner,
                    assertions_table.c.scope == "user",
                )
            )
            .mappings()
            .all()
        )
        assert len(user_rows) == 1
        assert user_rows[0]["status"] == "active"
        assert user_rows[0]["normalized_value"] == "quiet"


def test_read_engine_unrelated_key_abstention_e2e(clean, runtime_engine):
    uow = PostgresMemoryUnitOfWork(runtime_engine)
    store = PostgresMemoryStore(runtime_engine)
    engine = MemoryReadEngine(store, clock=lambda: NOW)
    owner = "owner_e2e_abstain"

    # Add hotel atmosphere
    _apply(
        uow,
        owner,
        MemoryOperation.ADD,
        _identity(owner, HOTEL_ATMOSPHERE_KEY),
        new_version=_draft(owner, HOTEL_ATMOSPHERE_KEY, "quiet"),
        idempotency_key="idemp_abs_1",
    )

    # Request key that does not exist for this user
    selection = engine.select(
        MemoryReadRequest(
            owner_user_id=owner,
            requested_keys=(TRAVEL_PACE_KEY,),
        )
    )
    assert selection.selected == ()
    assert selection.abstention_reason == AbstentionReason.NO_ELIGIBLE_MEMORY
