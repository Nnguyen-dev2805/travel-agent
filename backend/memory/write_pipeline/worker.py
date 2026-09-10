"""Background outbox worker runtime for memory candidate extraction.

Adheres to ADR 0014:
- Short lease transactions
- Extraction called strictly OUTSIDE the database transaction
- Pre-model secret scan prevents credential leak to generative models
- Revalidation of source conversation existence, retention state, and deletion epoch
- Cancellation if source conversation is deleted
- Error classification: transient errors retry with bounded exponential backoff;
  permanent errors transition directly to DEAD_LETTER
- Zero active versions created: all background extractions result in immutable
  shadow evidence / decisions only
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
import logging
from typing import Any, Protocol, Sequence, runtime_checkable

from backend.memory.write_pipeline.models import (
    Authority,
    DecisionOutcome,
    DecisionReason,
    MemoryCandidate,
    MemoryChangeSet,
    MemoryDecisionDraft,
    MemoryEvidence,
    MemoryOperation,
    assertion_identity,
    new_evidence_id,
)
from backend.memory.write_pipeline.outbox import (
    OutboxEvent,
    OutboxRepository,
    OutboxStatus,
    calculate_backoff,
)
from backend.memory.write_pipeline.model_adapter import (
    CostEvidence,
    ProviderPermanentError,
    ProviderTransientError,
    TokenUsage,
)
from backend.memory.write_pipeline.policy import (
    Actor,
    DecisionContext,
    Origin,
    decide_candidate,
)
from backend.memory.write_pipeline.secrets import detect_prohibited_content
from backend.memory.write_pipeline.uow import MemoryUnitOfWork
from backend.security.models import AuthenticatedPrincipal, AuthMode

logger = logging.getLogger("travel_agent_memory_worker")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class ConversationMessageReader(Protocol):
    """Protocol for reading conversation transcript ranges without leaking storage details."""

    def get_messages_in_range(
        self,
        conversation_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> Sequence[Any]: ...


@dataclass(frozen=True)
class WorkerResult:
    """Outcome of processing one outbox event."""

    status: OutboxStatus
    decision: DecisionOutcome | None = None
    error: str | None = None
    candidates_count: int = 0
    token_usage: TokenUsage | None = None
    cost_evidence: CostEvidence | None = None
    prompt_version: str | None = None
    schema_version: str | None = None


class MemoryOutboxWorker:
    """Consumes transactional outbox events and executes shadow memory extraction."""

    def __init__(
        self,
        outbox_repo: OutboxRepository,
        model_adapter: Any,
        uow: MemoryUnitOfWork,
        conversation_service: Any,
        recorder: Any = None,
        worker_id: str = "memory_worker_1",
        lease_duration_seconds: float = 30.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 2.0,
    ) -> None:
        self._outbox_repo = outbox_repo
        self._model_adapter = model_adapter
        self._uow = uow
        self._conversation_service = conversation_service
        self._recorder = recorder
        self._worker_id = worker_id
        self._lease_duration_seconds = lease_duration_seconds
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds


    @property
    def worker_id(self) -> str:
        return self._worker_id

    def run_batch(
        self,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> list[WorkerResult]:
        """Claim and process a batch of ready outbox events adhering to serialization rules."""
        now = utc_now()
        events = self._outbox_repo.claim_batch(
            lease_owner=self._worker_id,
            lease_duration_seconds=self._lease_duration_seconds,
            now=now,
            limit=limit,
            debounce_seconds=debounce_seconds,
        )
        results: list[WorkerResult] = []
        for event in events:
            results.append(self.process_one(event))
        return results

    def poll_once(
        self,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> int:
        """Poll and run a single batch, returning the count of events processed."""
        results = self.run_batch(limit=limit, debounce_seconds=debounce_seconds)
        return len(results)

    def process_one(self, event: OutboxEvent) -> WorkerResult:
        """Process a single outbox event through the safe shadow lifecycle."""
        now = utc_now()

        # 1. Lease management: Ensure event is leased to this worker
        stored = self._outbox_repo.get_event(event.outbox_id)
        if stored is not None:
            event = stored

        if event.status == OutboxStatus.CANCELLED:
            return WorkerResult(
                status=OutboxStatus.CANCELLED,
                decision=None,
                error="already_cancelled",
                candidates_count=0,
            )

        if event.status == OutboxStatus.SUCCEEDED:
            return WorkerResult(
                status=OutboxStatus.SUCCEEDED,
                decision=None,
                error="already_succeeded",
                candidates_count=0,
            )

        if event.status == OutboxStatus.DEAD_LETTER:
            return WorkerResult(
                status=OutboxStatus.DEAD_LETTER,
                decision=None,
                error="already_dead_letter",
                candidates_count=0,
            )

        if event.status == OutboxStatus.PENDING:
            if hasattr(self._outbox_repo, "claim_event"):
                claimed = self._outbox_repo.claim_event(
                    outbox_id=event.outbox_id,
                    lease_owner=self._worker_id,
                    lease_duration_seconds=self._lease_duration_seconds,
                    now=now,
                )
                if claimed is None:
                    return WorkerResult(
                        status=OutboxStatus.CANCELLED,
                        decision=None,
                        error="lease_claim_failed",
                        candidates_count=0,
                    )
                event = claimed
            else:
                event = replace(
                    event,
                    status=OutboxStatus.LEASED,
                    lease_owner=self._worker_id,
                    lease_until=now + timedelta(seconds=self._lease_duration_seconds),
                    attempt_count=event.attempt_count + 1,
                    updated_at=now,
                )
                self._outbox_repo.save_event(event)
        elif event.status == OutboxStatus.LEASED:
            if event.lease_owner != self._worker_id:
                return WorkerResult(
                    status=OutboxStatus.LEASED,
                    decision=None,
                    error="leased_by_another_worker",
                    candidates_count=0,
                )
            if event.lease_until is not None and event.lease_until < now:
                if hasattr(self._outbox_repo, "claim_event"):
                    claimed = self._outbox_repo.claim_event(
                        outbox_id=event.outbox_id,
                        lease_owner=self._worker_id,
                        lease_duration_seconds=self._lease_duration_seconds,
                        now=now,
                    )
                    if claimed is None:
                        return WorkerResult(
                            status=OutboxStatus.LEASED,
                            decision=None,
                            error="lease_renewal_failed",
                            candidates_count=0,
                        )
                    event = claimed

        # 2. Revalidate source conversation existence and deletion state
        conv = self._conversation_service.get_conversation(event.conversation_id)
        if conv is None:
            self._outbox_repo.cancel_events(
                event.conversation_id, reason="conversation_not_found", now=now
            )
            return WorkerResult(
                status=OutboxStatus.CANCELLED,
                decision=None,
                error="conversation_not_found",
                candidates_count=0,
            )

        retention = getattr(conv, "retention_state", None)
        if retention is None and isinstance(conv, dict):
            retention = conv.get("retention_state")

        if retention:
            ret_val = retention.value if hasattr(retention, "value") else str(retention)
            if ret_val in ("deleted", "deletion_requested"):
                self._outbox_repo.cancel_events(
                    event.conversation_id, reason="conversation_deleted", now=now
                )
                return WorkerResult(
                    status=OutboxStatus.CANCELLED,
                    decision=None,
                    error="conversation_deleted",
                    candidates_count=0,
                )

        # 3. Check deletion epoch
        if hasattr(self._conversation_service, "get_deletion_epoch"):
            current_epoch = self._conversation_service.get_deletion_epoch(
                event.conversation_id
            )
            expected_epoch = event.payload.get("deletion_epoch", 0)
            if current_epoch > expected_epoch and expected_epoch != 0:
                self._outbox_repo.cancel_events(
                    event.conversation_id, reason="deletion_epoch_advanced", now=now
                )
                return WorkerResult(
                    status=OutboxStatus.CANCELLED,
                    decision=None,
                    error="deletion_epoch_advanced",
                    candidates_count=0,
                )

        # 4. Gather messages for this conversation range using cursor when available
        after_sequence = None
        if isinstance(event.payload, dict):
            after_sequence = event.payload.get("after_sequence")
            if after_sequence is None and "after_message_id" in event.payload:
                after_msg_id = event.payload.get("after_message_id")
                if after_msg_id and hasattr(self._conversation_service, "get_message"):
                    msg = self._conversation_service.get_message(after_msg_id)
                    if msg is not None and hasattr(msg, "sequence"):
                        after_sequence = msg.sequence

        messages = self._load_messages(event.conversation_id, after_sequence=after_sequence)

        # 5. Pre-model deterministic secret scan across all message contents
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and detect_prohibited_content(content) is not None:
                logger.warning(
                    "Pre-model secret scan detected prohibited content; rejecting without model call conversation_id=%s outbox_id=%s",
                    event.conversation_id,
                    event.outbox_id,
                )
                self._outbox_repo.mark_succeeded(
                    event.outbox_id, lease_owner=self._worker_id, now=now
                )
                return WorkerResult(
                    status=OutboxStatus.SUCCEEDED,
                    decision=DecisionOutcome.REJECTED,
                    error="prohibited_content",
                    candidates_count=0,
                )

        prompt_version = getattr(self._model_adapter, "prompt_version", None)
        schema_version = getattr(self._model_adapter, "schema_version", None)

        # 6. Execute model extraction OUTSIDE any database transaction
        try:
            candidates = self._model_adapter.extract(
                messages,
                owner_user_id=event.owner_user_id,
                conversation_id=event.conversation_id,
            )
        except ProviderTransientError as err:
            logger.warning(
                "Transient model extraction error for outbox_id=%s: %s",
                event.outbox_id,
                err,
            )
            backoff = calculate_backoff(
                event.attempt_count,
                base_seconds=self._backoff_base_seconds,
            )
            new_status = self._outbox_repo.mark_failed(
                event.outbox_id,
                lease_owner=self._worker_id,
                error_message=str(err),
                retryable=True,
                max_attempts=self._max_attempts,
                backoff_seconds=backoff,
                now=now,
            )
            return WorkerResult(
                status=new_status,
                decision=None,
                error=str(err),
                candidates_count=0,
                token_usage=getattr(self._model_adapter, "last_token_usage", None),
                cost_evidence=getattr(self._model_adapter, "last_cost_evidence", None),
                prompt_version=prompt_version,
                schema_version=schema_version,
            )
        except ProviderPermanentError as err:
            logger.error(
                "Permanent model extraction error for outbox_id=%s: %s",
                event.outbox_id,
                err,
            )
            new_status = self._outbox_repo.mark_failed(
                event.outbox_id,
                lease_owner=self._worker_id,
                error_message=str(err),
                retryable=False,
                max_attempts=self._max_attempts,
                now=now,
            )
            return WorkerResult(
                status=new_status,
                decision=None,
                error=str(err),
                candidates_count=0,
                token_usage=getattr(self._model_adapter, "last_token_usage", None),
                cost_evidence=getattr(self._model_adapter, "last_cost_evidence", None),
                prompt_version=prompt_version,
                schema_version=schema_version,
            )
        except Exception as err:
            logger.error(
                "Unexpected error during model extraction for outbox_id=%s: %s",
                event.outbox_id,
                err,
            )
            new_status = self._outbox_repo.mark_failed(
                event.outbox_id,
                lease_owner=self._worker_id,
                error_message=str(err),
                retryable=False,
                max_attempts=self._max_attempts,
                now=now,
            )
            return WorkerResult(
                status=new_status,
                decision=None,
                error=str(err),
                candidates_count=0,
                token_usage=getattr(self._model_adapter, "last_token_usage", None),
                cost_evidence=getattr(self._model_adapter, "last_cost_evidence", None),
                prompt_version=prompt_version,
                schema_version=schema_version,
            )

        token_usage = getattr(self._model_adapter, "last_token_usage", None)
        cost_evidence = getattr(self._model_adapter, "last_cost_evidence", None)

        # 7. Revalidate lease before candidate persistence to eliminate stale commit hazard
        current_now = utc_now()
        fresh_event = self._outbox_repo.get_event(event.outbox_id)
        if (
            fresh_event is None
            or fresh_event.status != OutboxStatus.LEASED
            or fresh_event.lease_owner != self._worker_id
            or (fresh_event.lease_until is not None and fresh_event.lease_until <= current_now)
        ):
            logger.warning(
                "Lease lost or expired before candidate persistence outbox_id=%s worker=%s",
                event.outbox_id,
                self._worker_id,
            )
            return WorkerResult(
                status=fresh_event.status if fresh_event else OutboxStatus.CANCELLED,
                decision=None,
                error="lease_lost_before_commit",
                candidates_count=0,
                token_usage=token_usage,
                cost_evidence=cost_evidence,
                prompt_version=prompt_version,
                schema_version=schema_version,
            )

        # Apply shadow candidate persistence through service or UoW
        principal = AuthenticatedPrincipal(
            owner_user_id=event.owner_user_id,
            auth_mode=AuthMode.AUTHENTICATED,
            credential_label="internal_worker",
        )

        last_decision_outcome = None
        for candidate in candidates:
            ctx = DecisionContext(
                actor=Actor.USER,
                authenticated=True,
                origin=Origin.BACKGROUND_CHAT,
                source_deleted=False,
            )
            evidence = MemoryEvidence(
                evidence_id=new_evidence_id(),
                owner_user_id=event.owner_user_id,
                conversation_id=event.conversation_id,
                source_message_id=event.message_id,
                display_text=candidate.display_text,
                authority=candidate.authority,
                observed_at=candidate.observed_at or current_now,
            )

            if self._recorder is not None and hasattr(self._recorder, "record_sync"):
                rec_res = self._recorder.record_sync(candidate)
                last_decision_outcome = rec_res.decision_outcome
            elif self._recorder is not None and hasattr(self._recorder, "record"):
                import asyncio
                if asyncio.iscoroutinefunction(self._recorder.record):
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            import concurrent.futures
                            with concurrent.futures.ThreadPoolExecutor() as pool:
                                rec_res = pool.submit(asyncio.run, self._recorder.record(candidate)).result()
                        else:
                            rec_res = loop.run_until_complete(self._recorder.record(candidate))
                    except RuntimeError:
                        rec_res = asyncio.run(self._recorder.record(candidate))
                else:
                    rec_res = self._recorder.record(candidate)
                last_decision_outcome = rec_res.decision_outcome
            else:
                decision = decide_candidate(candidate, ctx)
                last_decision_outcome = decision.outcome
                change = MemoryChangeSet(
                    operation=MemoryOperation.NOOP,
                    identity=assertion_identity(candidate),
                    new_version=None,
                    superseded_version_ids=(),
                    reference_version_id=None,
                    reason=(
                        decision.reason.value
                        if hasattr(decision.reason, "value")
                        else str(decision.reason)
                    ),
                )
                self._uow.apply_memory_change(
                    change,
                    principal,
                    evidence=(evidence,),
                    decision=decision,
                    idempotency_key=f"bg_{event.outbox_id}_{candidate.candidate_id}",
                )

        # 8. Mark outbox event succeeded and check return value
        succeeded = self._outbox_repo.mark_succeeded(
            event.outbox_id,
            lease_owner=self._worker_id,
            now=current_now,
        )
        if not succeeded:
            logger.error(
                "Failed to mark outbox event %s succeeded; lease lost",
                event.outbox_id,
            )
            return WorkerResult(
                status=OutboxStatus.CANCELLED,
                decision=None,
                error="mark_succeeded_failed_lease_lost",
                candidates_count=len(candidates),
                token_usage=token_usage,
                cost_evidence=cost_evidence,
                prompt_version=prompt_version,
                schema_version=schema_version,
            )

        return WorkerResult(
            status=OutboxStatus.SUCCEEDED,
            decision=last_decision_outcome if candidates else None,
            error=None,
            candidates_count=len(candidates),
            token_usage=token_usage,
            cost_evidence=cost_evidence,
            prompt_version=prompt_version,
            schema_version=schema_version,
        )

    def _load_messages(
        self,
        conversation_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Load messages from conversation service adhering to ConversationMessageReader."""
        if hasattr(self._conversation_service, "get_messages_in_range"):
            raw_messages = self._conversation_service.get_messages_in_range(
                conversation_id, after_sequence=after_sequence, limit=limit
            )
        elif hasattr(self._conversation_service, "list_messages"):
            from backend.conversations.models import MessageHistoryQuery

            try:
                raw_messages = self._conversation_service.list_messages(
                    MessageHistoryQuery(
                        conversation_id=conversation_id,
                        limit=limit,
                    )
                )
            except Exception:
                try:
                    raw_messages = self._conversation_service.list_messages(
                        conversation_id, after_sequence=after_sequence, limit=limit
                    )
                except Exception:
                    raw_messages = ()
        elif hasattr(self._conversation_service, "get_messages"):
            raw_messages = self._conversation_service.get_messages(conversation_id)
        else:
            raw_messages = []

        messages: list[dict[str, Any]] = []
        for msg in raw_messages:
            if isinstance(msg, dict):
                seq = msg.get("sequence")
                if after_sequence is not None and seq is not None and seq <= after_sequence:
                    continue
                messages.append(msg)
            else:
                seq = getattr(msg, "sequence", None)
                if after_sequence is not None and seq is not None and seq <= after_sequence:
                    continue
                messages.append({
                    "message_id": getattr(msg, "message_id", ""),
                    "sequence": seq,
                    "role": (
                        getattr(msg.role, "value", str(msg.role))
                        if hasattr(msg, "role")
                        else "user"
                    ),
                    "content": getattr(msg, "content", ""),
                })
        return messages
