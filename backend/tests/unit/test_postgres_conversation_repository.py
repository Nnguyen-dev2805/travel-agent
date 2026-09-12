"""Unit tests for PostgreSQL conversation repository transactions.

These pin behaviors that live PG tests also cover, so the suite still
guards them when no database is available: tenant binding order and
fail-closed on blank owner, delete-propagation statements in one
transaction, and fence verification branches.
"""

import pytest

from backend.conversations.models import Conversation, utc_now
from backend.conversations.postgres_repository import PostgresConversationRepository
from backend.memory.write_pipeline.uow import FenceContext, FencedWriteError
from backend.storage.postgres import TenantContextError


class _FakeResult:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def mappings(self):
        return self

    def fetchone(self):
        return self._row

    def scalar_one_or_none(self):
        return self._row

    def scalar(self):
        # Mirrors require_tenant_context: the bound tenant echoes back.
        return self._row if isinstance(self._row, str) else "owner_a"


class _CM:
    def __init__(self, value):
        self._value = value

    def __enter__(self):
        return self._value

    def __exit__(self, *args):
        return False


class _FakeConnection:
    """Scripted connection: pops one result per execute, records SQL."""

    def __init__(self, script):
        self._script = list(script)
        self.statements = []

    def execution_options(self, **kwargs):
        return self

    def begin(self):
        return _CM(self)

    def execute(self, stmt, params=None):
        self.statements.append(str(stmt))
        assert self._script, f"unexpected execute: {stmt}"
        return self._script.pop(0)


class _FakeEngine:
    def __init__(self, connection):
        self._connection = connection

    def connect(self):
        return _CM(self._connection)


def _conversation():
    now = utc_now()
    return Conversation(
        conversation_id="cv_unit_1",
        owner_user_id="owner_a",
        title="Unit",
        created_at=now,
        updated_at=now,
    )


def test_tenant_binding_order_and_blank_owner_fails_closed():
    connection = _FakeConnection(
        [_FakeResult(), _FakeResult(), _FakeResult(rowcount=1)]
    )
    repo = PostgresConversationRepository(_FakeEngine(connection))

    repo.create(_conversation())

    assert "set_config" in connection.statements[0]
    assert "current_setting" in connection.statements[1]

    before = len(connection.statements)
    with pytest.raises(TenantContextError):
        repo.get("cv_unit_1", "   ")
    assert len(connection.statements) == before


def test_delete_issues_propagation_statements_in_one_transaction():
    connection = _FakeConnection(
        [
            _FakeResult(),
            _FakeResult(),
            _FakeResult(rowcount=1),
            _FakeResult(),
            _FakeResult(),
        ]
    )
    repo = PostgresConversationRepository(_FakeEngine(connection))

    assert repo.delete("cv_unit_1", "owner_a") is True

    sql = "\n".join(connection.statements)
    # Values travel as bound parameters; assert the statement shapes.
    assert "UPDATE conversations SET retention_state" in sql
    assert "UPDATE conversation_outbox SET status" in sql
    assert "UPDATE memory_evidence SET invalidated_at" in sql
    assert "deletion_epoch" in sql


def _fence(**overrides):
    payload = {
        "conversation_id": "cv_unit_1",
        "expected_epoch": 0,
        "outbox_id": "cout_unit_1",
        "lease_owner": "worker_1",
    }
    payload.update(overrides)
    return FenceContext(**payload)


def _fence_connection(conv_row, outbox_row):
    """Scripted connection for `_check_fence`.

    The outbox row carries `lease_held` — the lease-window verdict — rather than a
    `lease_until` the caller compares. `check_outbox_lease` computes that verdict
    from `now()` in the statement that reads the row (ADR 0032), so a double that
    supplies a raw timestamp would be modelling a fence that no longer exists.
    """
    from backend.memory.write_pipeline.postgres import PostgresMemoryUnitOfWork

    connection = _FakeConnection(
        [_FakeResult(row=conv_row), _FakeResult(row=outbox_row)]
    )
    return PostgresMemoryUnitOfWork, connection


def test_fence_accepts_live_lease():
    uow_cls, connection = _fence_connection(
        {"retention_state": "active", "deletion_epoch": 0},
        {"status": "leased", "lease_owner": "worker_1", "lease_held": True},
    )
    uow_cls._check_fence(connection, _fence(), "owner_a")  # must not raise


def test_fence_rejects_an_expired_lease():
    """Identity is not authority.

    The fence compared the holder and never `lease_until`, so a worker whose
    lease had already expired — but whose event had not been re-claimed — still
    passed and wrote Memory.
    """
    uow_cls, connection = _fence_connection(
        {"retention_state": "active", "deletion_epoch": 0},
        {
            "status": "leased",
            "lease_owner": "worker_1",
            # The window verdict, as `check_outbox_lease` computes it in SQL. An
            # expired window is `False`; the fence no longer compares a timestamp
            # the caller supplied (ADR 0032).
            "lease_held": False,
        },
    )
    with pytest.raises(FencedWriteError, match="expired"):
        uow_cls._check_fence(connection, _fence(), "owner_a")


def test_fence_rejects_gone_conversation():
    uow_cls, connection = _fence_connection(None, None)
    with pytest.raises(FencedWriteError, match="gone"):
        uow_cls._check_fence(connection, _fence(), "owner_a")


def test_fence_rejects_inactive_conversation():
    uow_cls, connection = _fence_connection(
        {"retention_state": "tombstoned", "deletion_epoch": 1},
        {"status": "leased", "lease_owner": "worker_1", "lease_held": True},
    )
    with pytest.raises(FencedWriteError, match="no longer active"):
        uow_cls._check_fence(connection, _fence(), "owner_a")


def test_fence_rejects_moved_epoch():
    uow_cls, connection = _fence_connection(
        {"retention_state": "active", "deletion_epoch": 2},
        {"status": "leased", "lease_owner": "worker_1", "lease_held": True},
    )
    with pytest.raises(FencedWriteError, match="epoch"):
        uow_cls._check_fence(connection, _fence(), "owner_a")


def test_fence_rejects_lost_lease():
    uow_cls, connection = _fence_connection(
        {"retention_state": "active", "deletion_epoch": 0},
        {"status": "cancelled", "lease_owner": None},
    )
    with pytest.raises(FencedWriteError, match="lease"):
        uow_cls._check_fence(connection, _fence(), "owner_a")


def test_fence_rejects_foreign_owner_row():
    """A row that is not the owner's must fence, never leak across tenants."""
    uow_cls, connection = _fence_connection(
        {"retention_state": "active", "deletion_epoch": 0},
        {"status": "leased", "lease_owner": "worker_1", "lease_held": True},
    )
    # Simulate the owner predicate filtering the row away: no row found.
    connection2 = _FakeConnection([_FakeResult(row=None), _FakeResult(row=None)])
    with pytest.raises(FencedWriteError):
        uow_cls._check_fence(connection2, _fence(), "owner_a")
