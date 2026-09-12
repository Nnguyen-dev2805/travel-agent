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
import json
import logging
from typing import Any, Protocol, Sequence, runtime_checkable

from backend.memory.write_pipeline.models import (
    DecisionOutcome,
)
from backend.memory.write_pipeline.outbox import (
    OutboxEvent,
    OutboxRepository,
    OutboxStatus,
    calculate_backoff,
)
from backend.memory.write_pipeline.uow import (
    FenceContext,
    FenceReason,
    FencedWriteError,
)
from backend.memory.write_pipeline.observability import WorkerReason
from backend.memory.write_pipeline.model_adapter import (
    CostEvidence,
    ProviderPermanentError,
    ProviderTransientError,
    TokenUsage,
)
from backend.memory.write_pipeline.secrets import detect_prohibited_content

# Imported for its governed vocabulary, not for its persistence: the worker must
# compare a message status against the enum member rather than a bare string, so
# the read filter cannot drift from the model it consumes. The event-family
# constant comes from the same module for the same reason — it is the vocabulary
# both the producer and this consumer share.
from backend.conversations.models import MEMORY_EXTRACT_EVENT_TYPE, MessageStatus

logger = logging.getLogger("travel_agent_memory_worker")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@runtime_checkable
class ConversationMessageReader(Protocol):
    """Protocol for reading conversation transcript ranges without leaking storage details."""

    def get_messages_in_range(
        self,
        conversation_id: str,
        owner_user_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
        until_sequence: int | None = None,
    ) -> Sequence[Any]: ...

    def get_deletion_epoch(
        self,
        conversation_id: str,
        owner_user_id: str,
    ) -> int: ...


@dataclass(frozen=True)
class WorkerResult:
    """Outcome of processing one outbox event."""

    status: OutboxStatus
    decision: DecisionOutcome | None = None
    #: Why the attempt ended this way. `None` means it succeeded.
    #:
    #: Typed, because the counters used to match two literal strings that the
    #: worker never emitted, so `lease_lost` could not increment. See
    #: `WorkerReason` for the vocabulary and `is_lease_loss` for the rule.
    reason: WorkerReason | None = None
    #: Unconstrained free text for diagnosis — a provider message, a fence reason,
    #: an event family. Never branched on; carried so a human can read the cause.
    error_detail: str | None = None
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
        conversation_service: ConversationMessageReader,
        recorder: Any,
        # Required, with no default. It used to default to the constant
        # `"memory_worker_1"`, which made two replicas indistinguishable: the
        # lease-holder test is `holder == lease_owner`, so one worker's lease loss
        # could clear or cancel the other's row. A default is a value a caller can
        # take by accident, so there is none — the identity comes from
        # `Settings.WORKER_ID`, which is derived from the process (ADR 0032).
        worker_id: str,
        lease_duration_seconds: float = 30.0,
        max_attempts: int = 3,
        backoff_base_seconds: float = 2.0,
    ) -> None:
        """Build the worker around the narrow `BackgroundMemoryRecorder` seam.

        The recorder is the only persistence path for extracted candidates:
        the worker never decides policy or writes versions itself. It exposes
        `record_sync`, which keeps the processing path synchronous and free of
        event-loop or thread-pool reflection.
        """
        if recorder is None:
            raise ValueError("A BackgroundMemoryRecorder is required.")
        self._outbox_repo = outbox_repo
        self._model_adapter = model_adapter
        self._conversation_service = conversation_service
        self._recorder = recorder
        self._worker_id = worker_id
        self._lease_duration_seconds = lease_duration_seconds
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def _lease_headroom_seconds(self) -> float:
        """How much lease must remain before a model call is worth starting.

        Half the configured lease, as a *ratio* rather than a measured latency on
        purpose: the right number depends on the provider, and a guess dressed up as
        a measurement is worse than an obvious rule. Calibrate it against observed
        extraction latency when tuning the worker.
        """
        return self._lease_duration_seconds / 2.0

    def _renew_lease_if_needed(self, event: OutboxEvent) -> bool:
        """Extend the lease when too little of it remains for a model call.

        Returns `False` when the lease could not be extended, which means stop:
        spending on an extraction the fence will refuse is the cost this exists to
        avoid.

        Safe whatever the local clock says, because the repository decides — it
        extends the window or reports that it could not. This is a local *estimate*
        of how much is left, used only to decide when to ask.
        """
        if event.lease_until is None:
            return True
        remaining = (event.lease_until - utc_now()).total_seconds()
        if remaining > self._lease_headroom_seconds():
            return True
        return self._outbox_repo.renew_lease(
            outbox_id=event.outbox_id,
            lease_owner=self._worker_id,
            lease_duration_seconds=self._lease_duration_seconds,
        )

    def _cancel_conversation_work(
        self, conversation_id: str, reason: FenceReason
    ) -> int:
        """Cancel a conversation's events, but only when the reason justifies it.

        The rule, in one place (ADR 0033): **cancel a conversation's remaining
        events only when the cause is a property of the conversation, never when
        it is a property of this worker's tenure.** The reason decides, so a
        future reason cannot cancel anything until it has been classified.

        This is called from the revalidation path only — the site that *first*
        observes an invalid conversation. The fence path cancels nothing: for the
        conversation-shaped reasons the invalidating transaction has already
        cancelled, and for the lease-shaped reasons cancelling would destroy
        another turn's valid work.
        """
        if not reason.cancels_conversation_work:
            logger.info(
                "Not cancelling conversation work reason=%s conversation_id=%s",
                reason.value,
                conversation_id,
            )
            return 0
        return self._outbox_repo.cancel_events(
            conversation_id, reason=reason.value
        )

    def run_batch(
        self,
        limit: int = 10,
        debounce_seconds: float = 0.0,
    ) -> list[WorkerResult]:
        """Claim and process a batch of ready outbox events adhering to serialization rules."""
        events = self._outbox_repo.claim_batch(
            lease_owner=self._worker_id,
            lease_duration_seconds=self._lease_duration_seconds,
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
        # The event family boundary, second layer. `claim_batch` and `claim_event`
        # filter on `event_type` in SQL, so this should be unreachable — which is
        # exactly why it is here and why it runs *first*. It is checked before the
        # lease is taken, so a future claim path that forgets the filter cannot
        # lease an event this worker would then extract from the wrong payload.
        #
        # `conversation_outbox` is one queue shared by every event family. The
        # Agent architecture introduces `agent.resume`, `summary.generate`,
        # `memory.reprocess` and others; without this, a Memory worker would
        # happily extract a conversation range out of one of them and report a
        # plausible success.
        if event.event_type != MEMORY_EXTRACT_EVENT_TYPE:
            logger.warning(
                "Refusing an outbox event of another family outbox_id=%s "
                "event_type=%s",
                event.outbox_id,
                event.event_type,
            )
            # The event's *own* status, not CANCELLED: it is not obsolete, it
            # belongs to another consumer, and the row is left untouched.
            return WorkerResult(
                status=event.status,
                decision=None,
                reason=WorkerReason.WRONG_EVENT_FAMILY,
                error_detail=event.event_type,
                candidates_count=0,
            )

        # 1. Lease management: Ensure event is leased to this worker
        stored = self._outbox_repo.get_event(event.outbox_id)
        if stored is not None:
            event = stored

        if event.status == OutboxStatus.CANCELLED:
            return WorkerResult(
                status=OutboxStatus.CANCELLED,
                decision=None,
                reason=WorkerReason.ALREADY_CANCELLED,
                candidates_count=0,
            )

        if event.status == OutboxStatus.SUCCEEDED:
            return WorkerResult(
                status=OutboxStatus.SUCCEEDED,
                decision=None,
                reason=WorkerReason.ALREADY_SUCCEEDED,
                candidates_count=0,
            )

        if event.status == OutboxStatus.DEAD_LETTER:
            return WorkerResult(
                status=OutboxStatus.DEAD_LETTER,
                decision=None,
                reason=WorkerReason.ALREADY_DEAD_LETTER,
                candidates_count=0,
            )

        if event.status == OutboxStatus.PENDING:
            if hasattr(self._outbox_repo, "claim_event"):
                claimed = self._outbox_repo.claim_event(
                    outbox_id=event.outbox_id,
                    lease_owner=self._worker_id,
                    lease_duration_seconds=self._lease_duration_seconds,
                )
                if claimed is None:
                    return WorkerResult(
                        status=OutboxStatus.CANCELLED,
                        decision=None,
                        reason=WorkerReason.LEASE_CLAIM_FAILED,
                        candidates_count=0,
                    )
                event = claimed
            else:
                # Fallback for a repository without an atomic claim — in practice
                # only the in-memory double. The clock here is the double's, not an
                # authority: the PostgreSQL repository claims and stamps the window
                # itself, from `now()`, so no application timestamp can extend a
                # lease (ADR 0032).
                local_now = utc_now()
                event = replace(
                    event,
                    status=OutboxStatus.LEASED,
                    lease_owner=self._worker_id,
                    lease_until=local_now
                    + timedelta(seconds=self._lease_duration_seconds),
                    attempt_count=event.attempt_count + 1,
                    updated_at=local_now,
                )
                self._outbox_repo.save_event(event)
        elif event.status == OutboxStatus.LEASED:
            if event.lease_owner != self._worker_id:
                return WorkerResult(
                    status=OutboxStatus.LEASED,
                    decision=None,
                    reason=WorkerReason.LEASED_BY_ANOTHER_WORKER,
                    candidates_count=0,
                )
            # This decides whether to *renew* the lease, not whether it is valid.
            # Validity is the repository's decision, and the fence decides it again
            # inside the write transaction. A wrong answer here costs a renewal
            # attempt or a skipped event; it can never extend a lease, because the
            # window is only ever written from the database clock (ADR 0032).
            if event.lease_until is not None and event.lease_until < utc_now():
                if hasattr(self._outbox_repo, "claim_event"):
                    claimed = self._outbox_repo.claim_event(
                        outbox_id=event.outbox_id,
                        lease_owner=self._worker_id,
                        lease_duration_seconds=self._lease_duration_seconds,
                    )
                    if claimed is None:
                        return WorkerResult(
                            status=OutboxStatus.LEASED,
                            decision=None,
                            reason=WorkerReason.LEASE_RENEWAL_FAILED,
                            candidates_count=0,
                        )
                    event = claimed

        # 2. Revalidate source conversation existence and deletion state
        conv = self._conversation_service.get_conversation(
            event.conversation_id, event.owner_user_id
        )
        if conv is None:
            self._cancel_conversation_work(
                event.conversation_id, FenceReason.CONVERSATION_GONE
            )
            return WorkerResult(
                status=OutboxStatus.CANCELLED,
                decision=None,
                reason=WorkerReason.CONVERSATION_NOT_FOUND,
                candidates_count=0,
            )

        retention = getattr(conv, "retention_state", None)
        if retention is None and isinstance(conv, dict):
            retention = conv.get("retention_state")

        if retention:
            ret_val = retention.value if hasattr(retention, "value") else str(retention)
            if ret_val in ("deleted", "deletion_requested"):
                self._cancel_conversation_work(
                    event.conversation_id, FenceReason.CONVERSATION_NOT_ACTIVE
                )
                return WorkerResult(
                    status=OutboxStatus.CANCELLED,
                    decision=None,
                    reason=WorkerReason.CONVERSATION_DELETED,
                    candidates_count=0,
                )

        # 3. Check deletion epoch
        if hasattr(self._conversation_service, "get_deletion_epoch"):
            current_epoch = self._conversation_service.get_deletion_epoch(
                event.conversation_id, event.owner_user_id
            )
            expected_epoch = event.payload.get("deletion_epoch", 0)
            if current_epoch > expected_epoch and expected_epoch != 0:
                self._cancel_conversation_work(
                    event.conversation_id, FenceReason.DELETION_EPOCH_MOVED
                )
                return WorkerResult(
                    status=OutboxStatus.CANCELLED,
                    decision=None,
                    reason=WorkerReason.DELETION_EPOCH_ADVANCED,
                    candidates_count=0,
                )

        # 4. Gather messages for this conversation range using cursor when available
        after_sequence = None
        until_sequence = None
        if isinstance(event.payload, dict):
            after_sequence = event.payload.get("after_sequence")
            # The event belongs to one turn. Without the upper bound a turn-1
            # event claimed after turn 2 was written read turn 2's messages and
            # attributed them to turn 1's provenance, and turn 2's own event read
            # them again.
            until_sequence = event.payload.get("until_sequence")
            if after_sequence is None and "after_message_id" in event.payload:
                after_msg_id = event.payload.get("after_message_id")
                if after_msg_id and hasattr(self._conversation_service, "get_message"):
                    msg = self._conversation_service.get_message(
                        after_msg_id, event.owner_user_id
                    )
                    if msg is not None and hasattr(msg, "sequence"):
                        after_sequence = msg.sequence

        messages = self._load_messages(
            event.conversation_id,
            event.owner_user_id,
            after_sequence=after_sequence,
            until_sequence=until_sequence,
        )

        # 5. Pre-model deterministic secret scan across all message contents.
        # Non-string block content is scanned in serialized form: structured
        # payloads reach the model prompt through string coercion, so scanning
        # only `str` would let embedded secrets bypass the gate.
        for msg in messages:
            content = msg.get("content", "")
            scannable = (
                content
                if isinstance(content, str)
                else json.dumps(content, ensure_ascii=False, default=str)
            )
            if detect_prohibited_content(scannable) is not None:
                logger.warning(
                    "Pre-model secret scan detected prohibited content; rejecting without model call conversation_id=%s outbox_id=%s",
                    event.conversation_id,
                    event.outbox_id,
                )
                self._outbox_repo.mark_succeeded(
                    event.outbox_id, lease_owner=self._worker_id
                )
                return WorkerResult(
                    status=OutboxStatus.SUCCEEDED,
                    decision=DecisionOutcome.REJECTED,
                    reason=WorkerReason.PROHIBITED_CONTENT,
                    candidates_count=0,
                )

        # 5b. Renew before paying for a model call, not after.
        #
        # `run_batch` claims the whole batch up front and processes it serially, so
        # the last event of a batch of ten can reach its model call with almost none
        # of its lease left. The fence protects correctness — a late write is refused
        # — but not cost: the provider is paid, and then the result is discarded.
        if not self._renew_lease_if_needed(event):
            logger.warning(
                "Lease could not be extended before the model call; not spending on "
                "an extraction that would be fenced outbox_id=%s worker=%s",
                event.outbox_id,
                self._worker_id,
            )
            return WorkerResult(
                status=OutboxStatus.LEASED,
                decision=None,
                reason=WorkerReason.LEASE_RENEWAL_FAILED,
                error_detail="no_headroom_before_model_call",
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
            )
            return WorkerResult(
                status=new_status,
                decision=None,
                reason=WorkerReason.PROVIDER_TRANSIENT,
                error_detail=str(err),
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
            )
            return WorkerResult(
                status=new_status,
                decision=None,
                reason=WorkerReason.PROVIDER_PERMANENT,
                error_detail=str(err),
                candidates_count=0,
                token_usage=getattr(self._model_adapter, "last_token_usage", None),
                cost_evidence=getattr(self._model_adapter, "last_cost_evidence", None),
                prompt_version=prompt_version,
                schema_version=schema_version,
            )
        except Exception as err:
            # Not adapter-raised, so the message is unconstrained: it may carry
            # provider, driver, or prompt text. Record the class only.
            logger.error(
                "Unexpected error during model extraction for outbox_id=%s failure_class=%s",
                event.outbox_id,
                type(err).__name__,
            )
            new_status = self._outbox_repo.mark_failed(
                event.outbox_id,
                lease_owner=self._worker_id,
                error_message=f"unexpected_failure class={type(err).__name__}",
                retryable=False,
                max_attempts=self._max_attempts,
            )
            return WorkerResult(
                status=new_status,
                decision=None,
                reason=WorkerReason.UNEXPECTED_FAILURE,
                error_detail=type(err).__name__,
                candidates_count=0,
                token_usage=getattr(self._model_adapter, "last_token_usage", None),
                cost_evidence=getattr(self._model_adapter, "last_cost_evidence", None),
                prompt_version=prompt_version,
                schema_version=schema_version,
            )

        token_usage = getattr(self._model_adapter, "last_token_usage", None)
        cost_evidence = getattr(self._model_adapter, "last_cost_evidence", None)

        # 7. Revalidate lease before candidate persistence, as a cheap early-out so
        # a lost lease does not pay for a doomed write. It is not the authority: the
        # fence re-checks the lease against database time inside the write
        # transaction. `current_now` is captured here and used only here, so it is
        # not stale — the defect ADR 0032 removed was reusing an entry-time value
        # after an unbounded model call.
        current_now = utc_now()
        fresh_event = self._outbox_repo.get_event(event.outbox_id)
        if (
            fresh_event is None
            or fresh_event.status != OutboxStatus.LEASED
            or fresh_event.lease_owner != self._worker_id
            or (
                fresh_event.lease_until is not None
                and fresh_event.lease_until <= current_now
            )
        ):
            logger.warning(
                "Lease lost or expired before candidate persistence outbox_id=%s worker=%s",
                event.outbox_id,
                self._worker_id,
            )
            return WorkerResult(
                status=fresh_event.status if fresh_event else OutboxStatus.CANCELLED,
                decision=None,
                reason=WorkerReason.LEASE_LOST_BEFORE_COMMIT,
                candidates_count=0,
                token_usage=token_usage,
                cost_evidence=cost_evidence,
                prompt_version=prompt_version,
                schema_version=schema_version,
            )

        # Apply shadow candidate persistence through the recorder seam.
        # The recorder derives its own idempotency key from the semantic
        # effect, so redelivery with freshly minted candidate ids still
        # deduplicates. The fence binds the commit to the lease and epoch
        # observed here; a delete landing after extraction fences the write
        # inside the same transaction instead of slipping through.
        fence = FenceContext(
            conversation_id=event.conversation_id,
            expected_epoch=int(event.payload.get("deletion_epoch", 0) or 0),
            outbox_id=event.outbox_id,
            lease_owner=self._worker_id,
        )
        last_decision_outcome = None
        for candidate in candidates:
            try:
                rec_res = self._recorder.record_sync(
                    candidate,
                    source_outbox_id=event.outbox_id,
                    source_message_id=event.message_id,
                    conversation_id=event.conversation_id,
                    fence=fence,
                )
            except FencedWriteError as fence_error:
                logger.warning(
                    "Memory write fenced reason=%s outbox_id=%s worker=%s: %s",
                    fence_error.reason.value,
                    event.outbox_id,
                    self._worker_id,
                    fence_error,
                )
                # A fence stops this worker. It cancels nothing (ADR 0033).
                #
                # This used to call `cancel_events`, which cancels every `PENDING`
                # row of the conversation. One of the fence's six causes is "this
                # worker lost its lease" — a fact about one worker's tenure, and
                # nothing about whether the conversation's other turns are valid.
                # Turn 2 and turn 3 were cancelled for it, permanently and
                # silently: `CANCELLED` is a legitimate terminal state, so the loss
                # was indistinguishable from a deliberate cancellation.
                #
                # The conversation-shaped causes need no repair here either: the
                # transaction that invalidated the conversation cancelled its
                # events in the same transaction, so a call would match zero rows.
                # Cancelling is the revalidation path's job, and only there —
                # because that is the site that *first observes* an invalid
                # conversation, with no prior transaction to have cancelled it.
                return WorkerResult(
                    status=OutboxStatus.CANCELLED,
                    decision=None,
                    reason=WorkerReason.FENCED_BY_SOURCE_MOVE,
                # The fence's own typed reason, so a lease loss and a deletion are
                # distinguishable in the log without parsing a message.
                error_detail=fence_error.reason.value,
                    candidates_count=0,
                    token_usage=token_usage,
                    cost_evidence=cost_evidence,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                )
            last_decision_outcome = rec_res.decision_outcome

        # 8. Mark outbox event succeeded and check return value
        succeeded = self._outbox_repo.mark_succeeded(
            event.outbox_id,
            lease_owner=self._worker_id,
        )
        if not succeeded:
            logger.error(
                "Failed to mark outbox event %s succeeded; lease lost",
                event.outbox_id,
            )
            return WorkerResult(
                status=OutboxStatus.CANCELLED,
                decision=None,
                reason=WorkerReason.MARK_SUCCEEDED_FAILED_LEASE_LOST,
                candidates_count=len(candidates),
                token_usage=token_usage,
                cost_evidence=cost_evidence,
                prompt_version=prompt_version,
                schema_version=schema_version,
            )

        return WorkerResult(
            status=OutboxStatus.SUCCEEDED,
            decision=last_decision_outcome if candidates else None,
            reason=None,
            candidates_count=len(candidates),
            token_usage=token_usage,
            cost_evidence=cost_evidence,
            prompt_version=prompt_version,
            schema_version=schema_version,
        )

    @staticmethod
    def _is_extractable(msg: Any) -> bool:
        """Return whether a message is finished and safe to extract from.

        Only a `complete` message is extractable. This is the second layer behind
        the ADR 0027 release gate: the gate stops a blocked event from being
        claimed, and this stops a non-terminal row from reaching the model even if
        one were handed over.

        A message that declares **no** status counts as extractable, because
        `Message.__post_init__` coerces an absent status to
        `MessageStatus.COMPLETE` (`backend/conversations/models.py:274-275`). The
        worker consumes that model, so applying a stricter rule here would make the
        same message complete to the repository and not-complete to the worker. A
        persisted message always carries a coerced status, so the branch is
        reachable only through a test double.
        """
        raw = msg.get("status") if isinstance(msg, dict) else getattr(msg, "status", None)
        if raw is None:
            return True
        return getattr(raw, "value", str(raw)) == MessageStatus.COMPLETE.value

    def _load_messages(
        self,
        conversation_id: str,
        owner_user_id: str,
        after_sequence: int | None = None,
        limit: int = 100,
        until_sequence: int | None = None,
    ) -> list[dict[str, Any]]:
        """Load owner-scoped messages through the conversation service contract.

        The range is `(after_sequence, until_sequence]`. The upper bound is passed
        to the service *and* re-applied here, because a service that does not
        honour the parameter must not silently widen the read.
        """
        raw_messages = self._conversation_service.get_messages_in_range(
            conversation_id,
            owner_user_id,
            after_sequence=after_sequence,
            limit=limit,
            until_sequence=until_sequence,
        )

        def in_range(seq: Any) -> bool:
            if seq is None:
                return True
            if after_sequence is not None and seq <= after_sequence:
                return False
            if until_sequence is not None and seq > until_sequence:
                return False
            return True

        messages: list[dict[str, Any]] = []
        for msg in raw_messages:
            if not self._is_extractable(msg):
                continue
            if isinstance(msg, dict):
                if not in_range(msg.get("sequence")):
                    continue
                messages.append(msg)
            else:
                seq = getattr(msg, "sequence", None)
                if not in_range(seq):
                    continue
                messages.append(
                    {
                        "message_id": getattr(msg, "message_id", ""),
                        "sequence": seq,
                        "role": (
                            getattr(msg.role, "value", str(msg.role))
                            if hasattr(msg, "role")
                            else "user"
                        ),
                        "content": getattr(msg, "content", ""),
                    }
                )
        return messages
