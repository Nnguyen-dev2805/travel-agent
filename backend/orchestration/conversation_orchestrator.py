"""Orchestration layer coordinating conversation persistence and RAG generation.

Per ADR 0005, ADR 0018, and ADR 0021:
Coordinates standalone conversation persistence, PostgreSQL semantic memory
outbox intent, and RAG generation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
)

from backend.conversations.models import (
    EPISODIC_EXTRACT_EVENT_TYPE,
    MEMORY_EXTRACT_EVENT_TYPE,
    WORKING_EXTRACT_EVENT_TYPE,
    ConversationValidationError,
    MessageRole,
    MessageSource,
    OutboxIntent,
    utc_now,
)
from backend.conversations.repository import (
    ConversationGoneError,
    ConversationRepositoryError,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingProposalOutcome,
    SourceHandlingOutcome,
    SourceHandlingProposal,
    SourceHandlingReason,
    SourceHandlingRecord,
    propose_source_handling,
)
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
)
from backend.orchestration.action_router import ActionRouter
from backend.orchestration.context_planner import ContextPlanner
from backend.orchestration.dialogue_state import DialogueStateResolver
from backend.orchestration.turn_models import (
    DURABLE_ACTION_MODES,
    InteractionMode,
    RoutingDecision,
    TurnDisposition,
)
from backend.orchestration.turn_understanding import TurnUnderstanding

if TYPE_CHECKING:  # pragma: no cover
    from backend.conversations.service import ConversationService

logger = logging.getLogger("travel_agent_orchestration")

DEFAULT_TOP_K = 4


#: No model produced this reply, so the label says so rather than borrowing the
#: configured model name — a model label must not be read as proof of a call.
INSPECT_UNAVAILABLE_MODEL = "unavailable"

#: Reading -> source-handling reason, written as an explicit table rather than
#: as an if-chain with a default. A chain has to end in *something*, and the
#: only useful default here would be "eligible" — which would mean a reading
#: added by a later stage inherits background permission simply because nobody
#: classified it. A table has no default: an unclassified reading raises.
#:
#: `EXPLICIT_INSPECT` maps to `EXPLICIT_ACTION` even though it mutates nothing.
#: The rule being applied is about a source that was already *handled* as an
#: explicit Memory command, not about whether that handling wrote anything
#: (`ADR 0038:61-64`); letting the worker independently reinterpret an
#: inspection request would make one source count twice.
_SOURCE_HANDLING_REASON_BY_READING: dict[InteractionMode, SourceHandlingReason] = {
    InteractionMode.NORMAL_QUERY: SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
    InteractionMode.EXPLICIT_REMEMBER: SourceHandlingReason.EXPLICIT_ACTION,
    InteractionMode.EXPLICIT_CORRECT: SourceHandlingReason.EXPLICIT_ACTION,
    InteractionMode.EXPLICIT_FORGET: SourceHandlingReason.EXPLICIT_ACTION,
    InteractionMode.EXPLICIT_INSPECT: SourceHandlingReason.EXPLICIT_ACTION,
    InteractionMode.AMBIGUOUS: SourceHandlingReason.AMBIGUOUS_INTENT,
}


def _source_handling_reason_for(
    interaction_mode: InteractionMode,
) -> SourceHandlingReason:
    """Map one Stage-1 reading onto the closed source-handling reason vocabulary.

    Only three of the four reasons are reachable from here. `SENSITIVE_BLOCKED`
    belongs to the stage that owns prohibited-content detection: reaching it
    would mean importing the write pipeline's detector into orchestration, which
    the approved plan forbids (`plan v0.6:456-459`).

    An unclassified reading raises rather than falling back to a reason. This is
    an authority boundary, so the two failure directions are not equivalent: a
    reading that is silently refused is a defect nobody notices until a family
    stops forming, whereas a reading that is silently *permitted* is the defect
    the whole architecture exists to prevent.
    """
    try:
        return _SOURCE_HANDLING_REASON_BY_READING[interaction_mode]
    except KeyError as error:
        raise ValueError(
            f"No source-handling reason is defined for the reading "
            f"'{interaction_mode}'. Classify it explicitly; an unclassified "
            f"reading must never inherit background eligibility."
        ) from error


class DialogueStateInvariantError(ConversationRepositoryError):
    """The turn could not reconstruct dialogue state for its own conversation.

    A mixed-conversation window is a failure of this server's composition, not
    something the caller did. Raised as a `ConversationRepositoryError` on
    purpose: the chat route maps that type to a content-free 500, whereas
    `ConversationValidationError` would surface an internal invariant failure to
    the user as a 422.
    """


class TurnTerminalWithoutContentError(ConversationRepositoryError):
    """This request did not write the turn, so the reply was never stored.

    Raised when `complete_turn` reports `applied=False`: the row was already
    terminal, so the transition this request asked for did not happen and the
    generated reply is nowhere. A second writer — a recovery actor, a resume actor,
    an agent state machine — moved the turn first.

    A `ConversationRepositoryError` subclass on purpose: the API already maps that
    type to a content-free 500, which is the right answer — from the client's point
    of view the reply failed to persist, whatever the reason.
    """


@dataclass(frozen=True)
class TurnPersistence:
    """What a bound turn managed to persist."""

    conversation_id: str
    user_message_id: Optional[str]
    assistant_message_id: Optional[str]
    persisted: bool


@dataclass(frozen=True)
class TurnOutcome:
    """The result of one chat turn.

    `disposition` is the internal reasoning outcome (ADR 0023 / `spec:332-363`).
    It stays on this aggregate and is never added to the public Chat response
    schema (`spec:360-363`).

    `source_handling` is the Stage-1 typed proposal for this turn's source
    (`plan v0.6:431-436`). It is internal for the same reason: it is evidence
    about how the turn was classified, not something a client may read. It is
    **not** a `SourceHandlingRecord` — orchestration cannot persist one, because
    it does not know the source's outbox identity (`spec:484-490`).
    """

    reply: str
    model: str
    citations: List[Dict[str, Any]]
    conversation: Optional[TurnPersistence] = None
    memory: Optional[Any] = None
    disposition: Optional[TurnDisposition] = None
    source_handling: Optional[SourceHandlingProposal] = None


class ConversationOrchestrator:
    """Coordinate conversation persistence and RAG generation for one turn."""

    def __init__(
        self,
        rag_service: Any,
        conversation_service_provider: Callable[[], "ConversationService"],
        top_k: int = DEFAULT_TOP_K,
        outbox_enabled: bool = False,
        context_planner: Optional[ContextPlanner] = None,
        explicit_actions_enabled: bool = False,
        explicit_action_handler: Optional[Any] = None,
        explicit_memory_commit: Optional[Any] = None,
        source_handling_recorder: Optional[Callable[[str, Any], bool]] = None,
        memory_read_engine: Optional[Any] = None,
        context_arbiter: Optional[Any] = None,
        memory_read_enabled: bool = False,
        memory_use_enabled: bool = False,
        episodic_read_engine: Optional[Any] = None,
        episodic_read_enabled: bool = False,
        working_read_engine: Optional[Any] = None,
        working_read_enabled: bool = False,
        working_state_writer: Optional[Callable[[Any], Any]] = None,
        working_write_enabled: bool = False,
        **_ignored: Any,
    ) -> None:
        self._rag_service = rag_service
        self._conversation_service_provider = conversation_service_provider
        self._top_k = top_k
        self._outbox_enabled = outbox_enabled
        self._dialogue_state = DialogueStateResolver()
        self._understanding = TurnUnderstanding()
        self._router = ActionRouter()
        # The rollout gate is a composition-root decision: this module may not
        # import `backend.app`, so the planner arrives injected and defaults to
        # the shadow-only one. That default is the safe one — enforcement may only
        # be switched on after the zero-false-`NONE` gate is conclusive.
        self._planner = context_planner if context_planner is not None else ContextPlanner()
        self._explicit_actions_enabled = explicit_actions_enabled
        self._explicit_action_handler = explicit_action_handler
        self._explicit_memory_commit = explicit_memory_commit
        self._source_handling_recorder = source_handling_recorder
        self._memory_read_engine = memory_read_engine
        if context_arbiter is not None:
            self._context_arbiter = context_arbiter
        else:
            from backend.orchestration.context_arbiter import ContextArbiter
            self._context_arbiter = ContextArbiter()
        self._memory_read_enabled = memory_read_enabled
        self._memory_use_enabled = memory_use_enabled
        self._episodic_read_engine = episodic_read_engine
        self._episodic_read_enabled = episodic_read_enabled
        self._working_read_engine = working_read_engine
        self._working_read_enabled = working_read_enabled
        self._working_state_writer = working_state_writer
        self._working_write_enabled = working_write_enabled

    @property
    def context_planner(self) -> ContextPlanner:
        """The planner this orchestrator proposes with.

        Read-only inspection point. The rollout gate is a composition-root
        decision, so whether it was actually wired can only be verified by
        reading the planner back.
        """
        return self._planner

    def _outbox_intents(self, *, payload: dict) -> tuple[OutboxIntent, ...]:
        """The family-specific outbox events one turn writes.

        One event per family, each with its own lease, idempotency and terminal
        state. They are written together, in the same transaction as the message,
        because the turn-readiness barrier releases each of them at completion;
        nothing here is shared between the families, so one family's failure or
        success says nothing about the other's.

        Emitting the episodic and working events is gated by the same
        background-capture flag as the semantic one, and that is the correct
        semantics rather than a convenience: `outbox_enabled` means "capture this
        turn's source for background formation", which is one act with
        family-specific consumers. What keeps each family safe is not this flag
        but that family's own activation gate, which is default-off, so captured
        episodic and working candidates stay shadow until their own evaluation
        passes.
        """
        intents = [
            OutboxIntent(event_type=MEMORY_EXTRACT_EVENT_TYPE, payload=payload)
        ]
        if self._outbox_enabled:
            intents.append(
                OutboxIntent(
                    event_type=EPISODIC_EXTRACT_EVENT_TYPE, payload=payload
                )
            )
            intents.append(
                OutboxIntent(
                    event_type=WORKING_EXTRACT_EVENT_TYPE, payload=payload
                )
            )
        return tuple(intents)

    def _read_working_selection(
        self, *, owner_user_id: str, conversation_id: str
    ) -> Any:
        """The eligible open state as it stood *before* this turn, or `None`.

        Read before the turn's own state is written, so a turn never feeds its own
        output back into its own context. `None` when the path is disabled, the
        engine is absent, or the read abstains — and `None` is the ordinary case,
        which is why the resolver's parameter defaults to it and why the arbiter's
        does too.
        """
        if (
            not self._working_read_enabled
            or self._working_read_engine is None
            or owner_user_id is None
            or conversation_id is None
        ):
            return None

        from backend.memory.working import WorkingReadRequest

        return self._working_read_engine.select(
            WorkingReadRequest(
                owner_user_id=owner_user_id, conversation_id=conversation_id
            )
        )

    @staticmethod
    def _working_context_from(selection: Any) -> Any:
        """Project an eligible selection into the resolver's structural type.

        The mapping lives here rather than in the resolver because the resolver is
        Stage-1 code and must not depend on a Memory family (`spec:327-328`).
        """
        if selection is None or not getattr(selection, "selected", ()):
            return None
        from backend.orchestration.dialogue_state import WorkingContext

        state = selection.selected[0]
        return WorkingContext(
            open_goal=str(state.open_goal),
            through_sequence=int(state.through_sequence),
        )

    def _write_deterministic_working_state(
        self,
        *,
        owner_user_id: str,
        conversation_id: str,
        recent_turns: Any,
        user_message: Any,
    ) -> None:
        """Persist this turn's deterministic open state, or refuse silently.

        The synchronous half of the two formation paths. It derives from the
        delivered turns — the recent window plus this turn's own user message —
        with no model call, which is what `spec:1037` calls a deterministic
        conversation transition. The worker's inferred replacement uses the same
        derivation over a bounded completed range, so both paths write through one
        replacement policy and one canonical row.

        The event identity is the turn's own outbox row when one exists, and a
        turn-local synthetic identity when it does not. A synthetic identity is
        honest here rather than a fake event: the deterministic path is not
        outbox-driven, and the identity exists only so a candidate can name its
        provenance.
        """
        if (
            not self._working_write_enabled
            or self._working_state_writer is None
            or owner_user_id is None
            or conversation_id is None
        ):
            return

        from backend.conversations.models import WORKING_EXTRACT_EVENT_TYPE
        from backend.memory.working import WorkingOrigin, WorkingStateTransition

        source_outbox_id = None
        if self._outbox_enabled:
            source_outbox_id = self._conversations_lookup_outbox_id(
                conversation_id, user_message.message_id, owner_user_id
            )
        if not source_outbox_id:
            source_outbox_id = f"turn_{user_message.message_id}"

        candidate = WorkingStateTransition().derive(
            turns=tuple(recent_turns) + (user_message,),
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            origin=WorkingOrigin.DETERMINISTIC_TRANSITION,
            source_outbox_id=source_outbox_id,
            source_message_id=user_message.message_id,
        )
        if candidate is None:
            return
        self._working_state_writer(candidate)

    def _conversations_lookup_outbox_id(
        self, conversation_id: str, message_id: str, owner_user_id: str
    ) -> str | None:
        """Read the WORKING event's id for this turn, when background capture wrote one."""
        from backend.conversations.models import WORKING_EXTRACT_EVENT_TYPE

        conversations = self._conversation_service_provider()
        return conversations.get_turn_outbox_id(
            conversation_id, message_id, owner_user_id, WORKING_EXTRACT_EVENT_TYPE
        )

    def _record_family_source_handling(
        self,
        conversations: Any,
        *,
        family: MemoryFamily,
        event_type: str,
        conversation_id: str,
        owner_user_id: str,
        user_message: Any,
        understanding: Any,
    ) -> None:
        """Persist one family's own authority for this source.

        One writer for every family, because the rule is one rule: the record must
        name the family whose event it authorizes, and a semantic record must
        never be able to authorize another family's formation. Two copies of this
        method would be two chances to bind the wrong event.

        Written after understanding, because eligibility depends on the
        interaction reading — which is only known once the turn has been
        persisted. That is still *before model exposure*: the event is released
        only by `complete_turn`, and the worker cannot claim an unreleased event,
        so a source can never reach a family's model without its record already
        existing.

        Only a positive outcome is recorded. There is no `BACKGROUND_BLOCKED`
        member in the durable outcome vocabulary, and inventing one would be a
        new contract; absence is `UNHANDLED`, which already denies, so a
        non-eligible source is refused by the same rule that refuses an unknown
        one.
        """
        if self._source_handling_recorder is None:
            return
        proposal = propose_source_handling(
            source_message_id=user_message.message_id,
            family=family,
            reason_code=_source_handling_reason_for(understanding.interaction_mode),
        )
        if proposal.outcome is not SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE:
            return
        source_outbox_id = conversations.get_turn_outbox_id(
            conversation_id,
            user_message.message_id,
            owner_user_id,
            event_type,
        )
        if not source_outbox_id:
            return
        self._source_handling_recorder(
            owner_user_id,
            SourceHandlingRecord(
                source_outbox_id=source_outbox_id,
                source_message_id=user_message.message_id,
                family=family,
                outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
                reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
                recorded_at=utc_now(),
            ),
        )

    def handle_turn(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        principal=None,
    ) -> TurnOutcome:
        """Run one chat turn, persisting it into the specified conversation."""
        from backend.conversations.service import ConversationNotFoundError

        if principal is None or not getattr(principal, "owner_user_id", None):
            raise ConversationNotFoundError("The conversation does not exist.")
        owner_user_id = principal.owner_user_id

        conversations = self._conversation_service_provider()

        if conversation_id is None:
            outbox_event: tuple[OutboxIntent, ...] | None = None
            if self._outbox_enabled or self._explicit_actions_enabled:
                outbox_event = self._outbox_intents(payload={})
            conversation, user_message, pending_message = (
                conversations.create_conversation_with_initial_turn(
                    owner_user_id=owner_user_id,
                    title=message[:60],
                    content=message,
                    role=MessageRole.USER,
                    source=MessageSource.UI,
                    outbox_event=outbox_event,
                )
            )
            conversation_id = conversation.conversation_id
        else:
            # Owner-scoped read: a missing or foreign conversation reads as absent,
            # so a bound turn never operates on another owner's transcript.
            conversation = conversations.get_conversation(
                conversation_id, owner_user_id
            )
            if conversation is None:
                # Compare against the AuthMode member (not a raw string) so the
                # authenticated branch cannot drift from the governed vocabulary.
                # Imported lazily: backend.security.__init__ pulls FastAPI, which
                # must stay out of this module's import-time graph.
                from backend.security.models import AuthMode, CrossOwnerAccessError

                if getattr(principal, "auth_mode", None) == AuthMode.AUTHENTICATED:
                    raise CrossOwnerAccessError(
                        "The conversation does not exist in this owner scope."
                    )
                raise ConversationNotFoundError("The conversation does not exist.")

            outbox_event: tuple[OutboxIntent, ...] | None = None
            if self._outbox_enabled or self._explicit_actions_enabled:
                outbox_event = self._outbox_intents(
                    payload={"conversation_id": conversation_id}
                )

            if outbox_event is not None:
                user_message, pending_message = conversations.append_turn(
                    conversation_id=conversation_id,
                    owner_user_id=owner_user_id,
                    user_content=message,
                    outbox_event=outbox_event,
                )
            else:
                user_message, pending_message = conversations.append_turn(
                    conversation_id=conversation_id,
                    owner_user_id=owner_user_id,
                    user_content=message,
                )

        # Phase one is committed: the user message and a pending assistant row
        # exist together, allocated under one parent-row lock, so turn adjacency
        # holds even when a concurrent turn commits in between (ADR 0023).

        # Everything from here to the terminal transition runs inside the failure
        # handler. Context reconstruction is included on purpose: a storage error
        # while reading the recent window is a failure of this turn, and leaving
        # it outside the `try` would skip `_fail_turn` and strand the pending
        # assistant row it just wrote.
        try:
            # Stage-1 context reconstruction, before generation and outside any
            # transaction. The window is bounded and read with `before_sequence`
            # set to this turn's own user message, so the current turn is never
            # part of its own history and a first turn resolves an empty state
            # (`plan v0.7:413-425`).
            recent_turns = conversations.get_recent_messages_before(
                conversation_id,
                owner_user_id,
                before_sequence=user_message.sequence,
            )
            working_selection = self._read_working_selection(
                owner_user_id=owner_user_id,
                conversation_id=conversation_id,
            )
            try:
                dialogue_state = self._dialogue_state.resolve(
                    recent_turns,
                    self._working_context_from(working_selection),
                )
            except ConversationValidationError as error:
                # The resolver refuses a window spanning more than one
                # conversation. That is this server's invariant failing, so it
                # must not leave here as the validation error the API answers
                # with a 422.
                raise DialogueStateInvariantError(
                    "Dialogue state could not be reconstructed for this turn."
                ) from error
            understanding = self._understanding.understand(message, dialogue_state)
            route = self._router.route(understanding)
            context_plan = self._planner.plan(understanding)

            # Task 5: record how this turn's source was handled. The proposal is
            # keyed by the user message this turn already persisted, so it names
            # a real source without orchestration having to reach for the
            # outbox identity that only the Stage-2 seam owns (`spec:484-490`).
            # It is evidence, not permission: nothing below consults it, and
            # Stage 1 creates no `SourceHandlingRecord`.
            source_handling = propose_source_handling(
                source_message_id=user_message.message_id,
                family=MemoryFamily.SEMANTIC,
                reason_code=_source_handling_reason_for(
                    understanding.interaction_mode
                ),
            )

            # Tasks 12-13: each additional family's authority is its own record,
            # bound to its own event. A semantic record never authorizes another
            # family's formation, so neither call is a duplicate of the proposal
            # above.
            # Task 13: the synchronous deterministic transition. No model call —
            # the open state is derived from delivered turns — and it runs through
            # the same replacement policy and canonical row as the worker's
            # inferred replacement.
            self._write_deterministic_working_state(
                owner_user_id=owner_user_id,
                conversation_id=conversation_id,
                recent_turns=recent_turns,
                user_message=user_message,
            )

            for family, event_type in (
                (MemoryFamily.EPISODIC, EPISODIC_EXTRACT_EVENT_TYPE),
                (MemoryFamily.WORKING, WORKING_EXTRACT_EVENT_TYPE),
            ):
                self._record_family_source_handling(
                    conversations,
                    family=family,
                    event_type=event_type,
                    conversation_id=conversation_id,
                    owner_user_id=owner_user_id,
                    user_message=user_message,
                    understanding=understanding,
                )

            # Shadow evidence only: the proposal is recorded, and the effective
            # mode stays the RAG-only baseline while enforcement is off. Nothing
            # below consults `context_plan.effective` to decide whether to
            # retrieve.
            logger.info(
                "chat.turn understood interaction_mode=%s route=%s "
                "proposed_context=%s effective_context=%s "
                "source_handling_family=%s source_handling_outcome=%s "
                "source_handling_reason=%s",
                understanding.interaction_mode.value,
                route.value,
                context_plan.proposed.value,
                context_plan.effective.value,
                source_handling.family.value,
                source_handling.outcome.value,
                source_handling.reason_code.value,
            )

            inspect_delivered = False
            if understanding.interaction_mode is InteractionMode.EXPLICIT_INSPECT:
                from backend.memory.explicit_actions import (
                    ExplicitMemoryActionHandler,
                    build_explicit_source_handling_record,
                )

                handler = self._explicit_action_handler or ExplicitMemoryActionHandler
                inspect_result = handler.inspect(
                    self._memory_read_engine,
                    owner_user_id=owner_user_id,
                    conversation_id=conversation_id,
                    memory_read_enabled=self._memory_read_enabled,
                )

                generated = {
                    "reply": inspect_result.reply,
                    "model": "system" if inspect_result.delivered else INSPECT_UNAVAILABLE_MODEL,
                    "citations": [],
                }
                inspect_delivered = inspect_result.delivered

                if self._explicit_actions_enabled and self._source_handling_recorder is not None:
                    source_outbox_id = conversations.get_turn_outbox_id(
                        conversation_id, user_message.message_id, owner_user_id
                    )
                    if source_outbox_id:
                        sh_rec = build_explicit_source_handling_record(
                            source_outbox_id=source_outbox_id,
                            source_message_id=user_message.message_id,
                            outcome=SourceHandlingOutcome.EXPLICIT_NOOP,
                            reason_code=SourceHandlingReason.EXPLICIT_ACTION,
                        )
                        self._source_handling_recorder(owner_user_id, sh_rec)
            elif (
                self._explicit_actions_enabled
                and self._explicit_action_handler is not None
                and route is RoutingDecision.EXPLICIT_MEMORY_ACTION
            ):
                from backend.memory.explicit_actions import (
                    ProposalOutcome,
                    build_explicit_source_handling_record,
                )
                proposal = self._explicit_action_handler.propose(
                    understanding,
                    dialogue_state,
                    owner_user_id=owner_user_id,
                    utterance=message,
                    conversation_id=conversation_id,
                )
                source_outbox_id = conversations.get_turn_outbox_id(
                    conversation_id, user_message.message_id, owner_user_id
                )

                if proposal.outcome is ProposalOutcome.NOOP:
                    reply_text = (
                        proposal.acknowledgement_text
                        or "Đã ghi nhận yêu cầu của bạn."
                    )
                    generated = {
                        "reply": reply_text,
                        "model": "system",
                        "citations": [],
                    }
                    if source_outbox_id and self._source_handling_recorder is not None:
                        sh_rec = build_explicit_source_handling_record(
                            source_outbox_id=source_outbox_id,
                            source_message_id=user_message.message_id,
                            outcome=SourceHandlingOutcome.EXPLICIT_NOOP,
                            reason_code=SourceHandlingReason.EXPLICIT_ACTION,
                        )
                        self._source_handling_recorder(owner_user_id, sh_rec)

                elif proposal.outcome is ProposalOutcome.CLARIFICATION:
                    reply_text = (
                        proposal.clarification_prompt
                        or "Tôi chưa hiểu rõ yêu cầu của bạn. Bạn có thể nói rõ hơn không?"
                    )
                    generated = {
                        "reply": reply_text,
                        "model": "system",
                        "citations": [],
                    }
                    if source_outbox_id and self._source_handling_recorder is not None:
                        sh_rec = build_explicit_source_handling_record(
                            source_outbox_id=source_outbox_id,
                            source_message_id=user_message.message_id,
                            outcome=SourceHandlingOutcome.EXPLICIT_REFUSED,
                            reason_code=SourceHandlingReason.AMBIGUOUS_INTENT,
                        )
                        self._source_handling_recorder(owner_user_id, sh_rec)

                elif proposal.outcome is ProposalOutcome.MUTATION:
                    if proposal.change is None or self._explicit_memory_commit is None:
                        raise RuntimeError(
                            "Explicit memory mutation proposal missing change or commit coordinator."
                        )
                    if source_outbox_id is None:
                        raise RuntimeError(
                            "Authoritative source_outbox_id missing for explicit memory mutation turn."
                        )

                    from backend.security.models import AuthenticatedPrincipal, AuthMode
                    from backend.memory.write_pipeline.uow import StaleVersionError

                    if isinstance(principal, AuthenticatedPrincipal):
                        auth_principal = principal
                    else:
                        auth_principal = AuthenticatedPrincipal(
                            owner_user_id=owner_user_id,
                            auth_mode=AuthMode.AUTHENTICATED,
                            credential_label=getattr(principal, "credential_label", "api") or "api",
                        )

                    expected_deletion_epoch = getattr(conversation, "deletion_epoch", 0)

                    def _build_commit_request(current_proposal):
                        return self._explicit_action_handler.build_commit_request(
                            proposal=current_proposal,
                            principal=auth_principal,
                            conversation_id=conversation_id,
                            user_message_id=user_message.message_id,
                            assistant_message_id=pending_message.message_id,
                            expected_deletion_epoch=expected_deletion_epoch,
                            source_outbox_id=source_outbox_id,
                            interaction_mode=understanding.interaction_mode,
                        )

                    commit_request = _build_commit_request(proposal)
                    try:
                        commit_result = self._explicit_memory_commit.commit(commit_request)
                    except StaleVersionError:
                        logger.warning(
                            "StaleVersionError on explicit turn; re-reading snapshot and retrying once."
                        )
                        recent_turns = conversations.get_recent_messages_before(
                            conversation_id,
                            owner_user_id,
                            before_sequence=user_message.sequence,
                        )
                        fresh_state = self._dialogue_state.resolve(recent_turns)
                        fresh_proposal = self._explicit_action_handler.propose(
                            understanding,
                            fresh_state,
                            owner_user_id=owner_user_id,
                            utterance=message,
                            conversation_id=conversation_id,
                        )
                        if (
                            fresh_proposal.outcome is not ProposalOutcome.MUTATION
                            or fresh_proposal.change is None
                        ):
                            raise
                        commit_request = _build_commit_request(fresh_proposal)
                        commit_result = self._explicit_memory_commit.commit(commit_request)

                    logger.info(
                        "chat.turn explicit_memory_persisted conversation_id=%s user_message_id=%s "
                        "assistant_message_id=%s persisted=%s",
                        conversation_id,
                        user_message.message_id,
                        pending_message.message_id,
                        True,
                    )
                    return TurnOutcome(
                        reply=commit_request.acknowledgement_text,
                        model="system",
                        citations=[],
                        conversation=TurnPersistence(
                            conversation_id=conversation_id,
                            user_message_id=user_message.message_id,
                            assistant_message_id=pending_message.message_id,
                            persisted=True,
                        ),
                        memory=commit_result.memory,
                    )
            else:
                # Generation runs outside any transaction. When planner enforcement
                # is enabled, generation uses the arbitrated context from ContextArbiter;
                # otherwise, the effective source plan stays the existing RAG-only baseline.
                generated = self._generate(
                    message,
                    plan=context_plan,
                    owner_user_id=owner_user_id,
                    conversation_id=conversation_id,
                    understanding=understanding,
                    working_selection=working_selection,
                )
        except Exception as error:
            # Phase two: record the failure rather than leaving an orphan turn.
            # `fail_turn` cancels this turn's outbox event in the same
            # transaction, so no extraction runs over an unanswered range.
            self._fail_turn(
                conversations,
                conversation_id=conversation_id,
                message_id=pending_message.message_id,
                owner_user_id=owner_user_id,
            )
            # Carry the conversation id so a first-turn failure can tell the
            # client which conversation to continue, instead of the client
            # creating a second one on retry (defect C2).
            try:
                error.conversation_id = conversation_id
            except AttributeError:  # pragma: no cover - exotic exception types
                logger.info(
                    "chat.turn failure_carries_no_conversation_id failure_class=%s",
                    type(error).__name__,
                )
            raise

        try:
            transition = conversations.complete_turn(
                conversation_id=conversation_id,
                message_id=pending_message.message_id,
                owner_user_id=owner_user_id,
                content=generated["reply"],
            )
        except ConversationGoneError as error:
            # The conversation vanished during generation: report absence
            # (404 upstream) instead of resurrecting content into a deleted
            # conversation.
            from backend.conversations.service import ConversationNotFoundError

            raise ConversationNotFoundError(
                "The conversation does not exist."
            ) from error
        except ConversationRepositoryError as error:
            # The turn stays `pending` and visible; the reply is not stored.
            # There is no automatic recovery in this change, so this is a
            # distinct observable failure rather than a degraded success.
            logger.error(
                "chat.turn persistence_incomplete conversation_id=%s "
                "assistant_message_id=%s stage=complete_turn failure_class=%s",
                conversation_id,
                pending_message.message_id,
                type(error).__name__,
            )
            raise

        assistant_message = transition.message

        # `applied` is the fact; the returned row is not. The repository is
        # idempotent — a row that is no longer `pending` comes back unchanged — so a
        # second writer can hand back a row that is `complete` carrying *someone
        # else's* content. Branching on the status alone would accept that row and
        # hand the client this request's reply while the database holds a different
        # one. Comparing `assistant_message.content` would infer ownership from a
        # value, which breaks the moment two turns legitimately produce the same
        # text; `applied` is the fact itself.
        if not transition.applied:
            logger.error(
                "chat.turn transition_not_applied conversation_id=%s "
                "assistant_message_id=%s stored_status=%s",
                conversation_id,
                assistant_message.message_id,
                getattr(assistant_message.status, "value", assistant_message.status),
            )
            raise TurnTerminalWithoutContentError(
                "The turn was already terminal when this request tried to complete "
                "it, so this reply was not stored."
            )

        logger.info(
            "chat.turn persisted conversation_id=%s user_message_id=%s "
            "assistant_message_id=%s persisted=%s",
            conversation_id,
            user_message.message_id,
            assistant_message.message_id,
            True,
        )
        return TurnOutcome(
            reply=generated["reply"],
            model=generated["model"],
            citations=generated["citations"],
            conversation=TurnPersistence(
                conversation_id=conversation_id,
                user_message_id=user_message.message_id,
                assistant_message_id=assistant_message.message_id,
                persisted=True,
            ),
            memory=None,
            disposition=self._disposition_for(route, inspect_delivered=inspect_delivered),
            source_handling=source_handling,
        )

    @staticmethod
    def _disposition_for(
        route: RoutingDecision,
        inspect_delivered: bool = False,
    ) -> TurnDisposition:
        """The honest reasoning outcome for a turn that did answer.

        Neither non-normal route achieved what the user asked. Stage 1 recognizes
        an explicit Memory action but cannot execute it — the handler is Task 8 —
        and it answers an ambiguous reading with an ordinary reply rather than
        asking a focused clarification. Reporting `ANSWERED` for either would be a
        false success (`spec:396-398`), so both report `INCOMPLETE`.

        When explicit inspect is successfully delivered via governed MemoryReadEngine,
        it reports `ANSWERED`.

        `NEEDS_CLARIFICATION` is deliberately not produced yet: the spec pairs it
        with an assistant message that actually asks a clarification
        (`spec:347-350`), and Stage 1 does not generate one. It becomes reachable
        when a stage does.

        `EXECUTION_FAILED` is not returned here either: this method is only
        reached when generation and the terminal transition both succeeded.
        """
        if route is RoutingDecision.NORMAL_QUERY or inspect_delivered:
            return TurnDisposition.ANSWERED
        return TurnDisposition.INCOMPLETE

    def _fail_turn(
        self,
        conversations: "ConversationService",
        *,
        conversation_id: str,
        message_id: str,
        owner_user_id: str,
    ) -> None:
        """Record a failed turn without masking the original generation error.

        If the failure record itself cannot be written, the generation error is
        still the one that propagates: a turn left `pending` is visible, whereas
        swallowing the original error would hide why it failed.
        """
        from backend.conversations.service import ConversationNotFoundError

        try:
            conversations.fail_turn(conversation_id, message_id, owner_user_id)
        except ConversationNotFoundError:
            logger.info(
                "chat.turn fail_skipped conversation_id=%s reason=conversation_gone",
                conversation_id,
            )
        except ConversationRepositoryError as error:
            logger.error(
                "chat.turn fail_skipped conversation_id=%s assistant_message_id=%s "
                "failure_class=%s",
                conversation_id,
                message_id,
                type(error).__name__,
            )

    def _generate(
        self,
        message: str,
        plan: Optional[Any] = None,
        owner_user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        understanding: Optional[Any] = None,
        working_selection: Optional[Any] = None,
    ) -> Dict[str, Any]:
        if not self._planner.enforcement_enabled or not hasattr(
            self._rag_service, "generate_from_context"
        ):
            return self._rag_service.generate_answer(message, top_k=self._top_k)

        from backend.orchestration.turn_models import ContextMode

        mode = plan.effective if plan is not None else ContextMode.RAG_ONLY

        rag_bundle = None
        if mode in (ContextMode.RAG_ONLY, ContextMode.BOTH):
            if hasattr(self._rag_service, "build_travel_context"):
                rag_bundle = self._rag_service.build_travel_context(
                    message, top_k=self._top_k
                )

        memory_selection = None
        if (
            mode in (ContextMode.MEMORY_ONLY, ContextMode.BOTH)
            and self._memory_read_enabled
            and self._memory_use_enabled
            and self._memory_read_engine is not None
            and owner_user_id is not None
        ):
            from backend.memory.read_models import MemoryReadRequest

            requested = (
                plan.requested_memory_keys
                if plan is not None
                else ()
            )
            if requested:
                req = MemoryReadRequest(
                    owner_user_id=owner_user_id,
                    conversation_id=conversation_id,
                    requested_keys=requested,
                    max_selected=8,
                )
                memory_selection = self._memory_read_engine.select(req)

        override_keys = (
            understanding.current_memory_override_keys
            if understanding is not None and hasattr(understanding, "current_memory_override_keys")
            else ()
        )
        # The episodic read is a separate typed contract, so it is a separate
        # selection rather than more `requested_memory_keys`: an episode has no
        # registry key, and giving it a fake one would make every semantic policy
        # apply to something it was never written for.
        episodic_selection = None
        if (
            mode in (ContextMode.MEMORY_ONLY, ContextMode.BOTH)
            and self._episodic_read_enabled
            and self._episodic_read_engine is not None
            and owner_user_id is not None
            and conversation_id is not None
        ):
            from datetime import datetime, timedelta, timezone

            from backend.memory.context import EPISODIC_LOOKBACK_DAYS
            from backend.memory.episodic import EpisodeReadRequest

            now = datetime.now(timezone.utc)
            episodic_selection = self._episodic_read_engine.select(
                EpisodeReadRequest(
                    owner_user_id=owner_user_id,
                    conversation_id=conversation_id,
                    occurred_after=now - timedelta(days=EPISODIC_LOOKBACK_DAYS),
                    occurred_before=now + timedelta(days=1),
                )
            )

        generation_context = self._context_arbiter.arbitrate(
            mode=mode,
            rag_bundle=rag_bundle,
            memory_selection=memory_selection,
            current_memory_override_keys=override_keys,
            episodic_selection=episodic_selection,
            working_selection=working_selection,
        )

        result = self._rag_service.generate_from_context(message, generation_context)

        return {
            "reply": result.reply,
            "citations": [
                {
                    "title": citation.title,
                    "url": citation.url,
                }
                for citation in result.citations
            ],
            "model": result.model,
        }
