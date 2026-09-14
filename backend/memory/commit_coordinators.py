"""Stage 2 Dual Commit Coordinators (ADR 0036, Plan v0.13 Task 7).

Coordinates explicit Chat-native Memory mutation and background Memory worker commits
over shared transaction-aware store and conversation primitives.

Canonical lock order:
conversation -> outbox (worker only) -> memory rows
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from backend.conversations.models import (
    MessageStatus,
    TransitionResult,
)
from backend.memory.source_handling import SourceHandlingRecord
from backend.memory.write_pipeline.models import (
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    SourceValidity,
)
from backend.memory.write_pipeline.uow import (
    FenceContext,
    FenceReason,
    FencedWriteError,
    MemoryWriteError,
    MemoryWriteResult,
    MemoryWriteStore,
)
from backend.security.models import AuthenticatedPrincipal

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection, Engine


class ExplicitTurnTransitionError(MemoryWriteError):
    """Guarded turn transition could not be applied; acknowledgement did not commit."""


@dataclass(frozen=True)
class ExplicitMemoryCommitRequest:
    principal: AuthenticatedPrincipal
    conversation_id: str
    assistant_message_id: str
    expected_deletion_epoch: int
    acknowledgement_text: str
    change: MemoryChangeSet
    evidence: tuple[MemoryEvidence, ...]
    decision: MemoryDecisionDraft | None
    idempotency_key: str
    expected_version_id: str | None
    source_validity: SourceValidity | None
    source_handling_record: SourceHandlingRecord


@dataclass(frozen=True)
class ExplicitMemoryCommitResult:
    memory: MemoryWriteResult
    transition: TransitionResult


@dataclass(frozen=True)
class BackgroundMemoryCommitRequest:
    principal: AuthenticatedPrincipal
    change: MemoryChangeSet
    evidence: tuple[MemoryEvidence, ...]
    decision: MemoryDecisionDraft | None
    idempotency_key: str
    expected_version_id: str | None
    source_validity: SourceValidity | None
    fence: FenceContext


class ExplicitMemoryTurnCommit:
    """API-owned transaction for atomic explicit Memory + acknowledgement + source-handling + guarded terminal turn commit.

    Canonical lock order:
    bind tenant
    -> validate/lock conversation + deletion_epoch
    -> memory rows
    """

    def __init__(
        self,
        engine: Engine | None = None,
        *,
        transaction_factory: Callable[[], Any] | None = None,
        bind_tenant_fn: Callable[[Any, str], None] | None = None,
        lock_conversation_fn: Callable[[Any, str, int, str | None], None] | None = None,
        memory_write_store: MemoryWriteStore | None = None,
        record_source_handling_fn: Callable[[Any, str, SourceHandlingRecord], bool] | None = None,
        transition_turn_fn: Callable[..., TransitionResult] | None = None,
    ) -> None:
        self._engine = engine
        self._transaction_factory = transaction_factory
        self._bind_tenant_fn = bind_tenant_fn
        self._lock_conversation_fn = lock_conversation_fn
        self._memory_write_store = memory_write_store
        self._record_source_handling_fn = record_source_handling_fn
        self._transition_turn_fn = transition_turn_fn

    def _get_transaction_context(self) -> Any:
        if self._transaction_factory is not None:
            return self._transaction_factory()
        if self._engine is not None:
            from backend.storage.postgres import transaction

            return transaction(self._engine)
        raise RuntimeError(
            "ExplicitMemoryTurnCommit requires an engine or transaction_factory."
        )

    def _get_bind_tenant(self) -> Callable[[Any, str], None]:
        if self._bind_tenant_fn is not None:
            return self._bind_tenant_fn
        from backend.conversations.postgres_repository import bind_tenant_on

        return bind_tenant_on

    def _get_lock_conversation(self) -> Callable[[Any, str, int, str | None], None]:
        if self._lock_conversation_fn is not None:
            return self._lock_conversation_fn
        from backend.conversations.postgres_repository import (
            lock_conversation_and_epoch,
        )

        return lock_conversation_and_epoch

    def _get_memory_write_store(self) -> MemoryWriteStore:
        if self._memory_write_store is not None:
            return self._memory_write_store
        if self._engine is not None:
            from backend.memory.write_pipeline.postgres import (
                PostgresMemoryUnitOfWork,
            )

            return PostgresMemoryUnitOfWork(self._engine)
        raise RuntimeError(
            "ExplicitMemoryTurnCommit requires memory_write_store or engine."
        )

    def _get_record_source_handling(
        self,
    ) -> Callable[[Any, str, SourceHandlingRecord], bool]:
        if self._record_source_handling_fn is not None:
            return self._record_source_handling_fn
        from backend.memory.write_pipeline.postgres import (
            record_source_handling_on,
        )

        return record_source_handling_on

    def _get_transition_turn(self) -> Callable[..., TransitionResult]:
        if self._transition_turn_fn is not None:
            return self._transition_turn_fn
        from backend.conversations.postgres_repository import transition_turn_on

        return transition_turn_on

    def commit(
        self, request: ExplicitMemoryCommitRequest
    ) -> ExplicitMemoryCommitResult:
        owner_user_id = request.principal.owner_user_id
        bind_tenant = self._get_bind_tenant()
        lock_conversation = self._get_lock_conversation()
        memory_store = self._get_memory_write_store()
        record_source_handling = self._get_record_source_handling()
        transition_turn = self._get_transition_turn()

        with self._get_transaction_context() as connection:
            # 1. Bind tenant
            bind_tenant(connection, owner_user_id)

            # 2. Lock conversation + validate deletion epoch
            lock_conversation(
                connection,
                request.conversation_id,
                request.expected_deletion_epoch,
                owner_user_id,
            )

            # 3. Apply memory change on caller connection (fence=None for explicit path)
            memory_result = memory_store.apply_on(
                connection,
                change=request.change,
                principal=request.principal,
                evidence=request.evidence,
                decision=request.decision,
                idempotency_key=request.idempotency_key,
                expected_version_id=request.expected_version_id,
                fence=None,
                source_validity=request.source_validity,
            )

            # 4. Record source handling authority record
            source_handling_applied = record_source_handling(
                connection,
                owner_user_id,
                request.source_handling_record,
            )

            # 5. Guarded turn transition with deterministic acknowledgement text
            transition_result = transition_turn(
                connection,
                request.conversation_id,
                request.assistant_message_id,
                owner_user_id,
                status=MessageStatus.COMPLETE,
                content=request.acknowledgement_text,
            )

            # Fail-closed if turn was already transitioned by another writer (ADR 0023).
            # "No durable mutation may become visible if the acknowledgement did not commit."
            # Distinguish exact idempotent replay from losing race:
            # An exact replay has an identical source handling record already recorded
            # (source_handling_applied is False) AND the assistant row is already COMPLETE
            # with the exact acknowledgement text.
            if not transition_result.applied:
                is_exact_replay = (
                    not source_handling_applied
                    and transition_result.message.status is MessageStatus.COMPLETE
                    and transition_result.message.content == request.acknowledgement_text
                )
                if not is_exact_replay:
                    raise ExplicitTurnTransitionError(
                        "Could not complete the turn acknowledgement; another writer already moved the turn."
                    )

            return ExplicitMemoryCommitResult(
                memory=memory_result,
                transition=transition_result,
            )


class BackgroundMemoryCommit:
    """Worker-owned transaction for fenced background semantic effect + source-event completion.

    Canonical lock order:
    bind tenant
    -> validate/lock conversation + deletion_epoch
    -> validate/lock outbox lease
    -> memory rows
    """

    def __init__(
        self,
        engine: Engine | None = None,
        *,
        transaction_factory: Callable[[], Any] | None = None,
        bind_tenant_fn: Callable[[Any, str], None] | None = None,
        lock_conversation_fn: Callable[[Any, str, int, str | None], None] | None = None,
        check_outbox_lease_fn: Callable[[Any, str, str], tuple[bool, Any]] | None = None,
        memory_write_store: MemoryWriteStore | None = None,
        mark_outbox_succeeded_fn: Callable[[Any, str, str], bool] | None = None,
    ) -> None:
        self._engine = engine
        self._transaction_factory = transaction_factory
        self._bind_tenant_fn = bind_tenant_fn
        self._lock_conversation_fn = lock_conversation_fn
        self._check_outbox_lease_fn = check_outbox_lease_fn
        self._memory_write_store = memory_write_store
        self._mark_outbox_succeeded_fn = mark_outbox_succeeded_fn

    def _get_transaction_context(self) -> Any:
        if self._transaction_factory is not None:
            return self._transaction_factory()
        if self._engine is not None:
            from backend.storage.postgres import transaction

            return transaction(self._engine)
        raise RuntimeError(
            "BackgroundMemoryCommit requires an engine or transaction_factory."
        )

    def _get_bind_tenant(self) -> Callable[[Any, str], None]:
        if self._bind_tenant_fn is not None:
            return self._bind_tenant_fn
        from backend.conversations.postgres_repository import bind_tenant_on

        return bind_tenant_on

    def _get_lock_conversation(self) -> Callable[[Any, str, int, str | None], None]:
        if self._lock_conversation_fn is not None:
            return self._lock_conversation_fn
        from backend.conversations.postgres_repository import (
            lock_conversation_and_epoch,
        )

        return lock_conversation_and_epoch

    def _get_check_outbox_lease(
        self,
    ) -> Callable[[Any, str, str], tuple[bool, Any]]:
        if self._check_outbox_lease_fn is not None:
            return self._check_outbox_lease_fn
        from backend.conversations.postgres_repository import check_outbox_lease

        return check_outbox_lease

    def _get_mark_outbox_succeeded(self) -> Callable[[Any, str, str], bool]:
        if self._mark_outbox_succeeded_fn is not None:
            return self._mark_outbox_succeeded_fn
        from backend.conversations.postgres_repository import (
            mark_outbox_succeeded_on,
        )

        return mark_outbox_succeeded_on

    def _get_memory_write_store(self) -> MemoryWriteStore:
        if self._memory_write_store is not None:
            return self._memory_write_store
        if self._engine is not None:
            from backend.memory.write_pipeline.postgres import (
                PostgresMemoryUnitOfWork,
            )

            return PostgresMemoryUnitOfWork(self._engine)
        raise RuntimeError(
            "BackgroundMemoryCommit requires memory_write_store or engine."
        )

    def commit(
        self, request: BackgroundMemoryCommitRequest
    ) -> MemoryWriteResult:
        owner_user_id = request.principal.owner_user_id
        fence = request.fence

        bind_tenant = self._get_bind_tenant()
        lock_conversation = self._get_lock_conversation()
        check_outbox_lease = self._get_check_outbox_lease()
        memory_store = self._get_memory_write_store()
        mark_outbox_succeeded = self._get_mark_outbox_succeeded()

        with self._get_transaction_context() as connection:
            # 1. Bind tenant
            bind_tenant(connection, owner_user_id)

            # 2. Lock conversation + validate deletion epoch
            lock_conversation(
                connection,
                fence.conversation_id,
                fence.expected_epoch,
                owner_user_id,
            )

            # 3. Validate outbox lease (worker-only fence)
            lease_ok, reason = check_outbox_lease(
                connection,
                fence.outbox_id,
                fence.lease_owner,
            )
            if not lease_ok:
                assert reason is not None
                raise FencedWriteError(reason)

            # 4. Apply memory mutation with fence
            memory_result = memory_store.apply_on(
                connection,
                change=request.change,
                principal=request.principal,
                evidence=request.evidence,
                decision=request.decision,
                idempotency_key=request.idempotency_key,
                expected_version_id=request.expected_version_id,
                fence=fence,
                source_validity=request.source_validity,
            )

            # 5. Mark outbox event as SUCCEEDED in the same transaction (ADR 0036)
            succeeded = mark_outbox_succeeded(
                connection,
                fence.outbox_id,
                fence.lease_owner,
            )
            if not succeeded:
                raise FencedWriteError(FenceReason.LEASE_LOST)

            return memory_result
