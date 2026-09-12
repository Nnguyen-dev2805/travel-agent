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
    MEMORY_EXTRACT_EVENT_TYPE,
    MessageRole,
    MessageSource,
    OutboxIntent,
)
from backend.conversations.repository import (
    ConversationGoneError,
    ConversationRepositoryError,
)
from backend.observability.events import emit_event
from backend.observability.models import (
    EventComponent,
    EventName,
    EventResult,
)

if TYPE_CHECKING:  # pragma: no cover
    from backend.conversations.service import ConversationService

logger = logging.getLogger("travel_agent_orchestration")

DEFAULT_TOP_K = 4


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
    """The result of one chat turn."""

    reply: str
    model: str
    citations: List[Dict[str, Any]]
    conversation: Optional[TurnPersistence] = None
    memory: Optional[Any] = None


class ConversationOrchestrator:
    """Coordinate conversation persistence and RAG generation for one turn."""

    def __init__(
        self,
        rag_service: Any,
        conversation_service_provider: Callable[[], "ConversationService"],
        top_k: int = DEFAULT_TOP_K,
        outbox_enabled: bool = False,
        **_ignored: Any,
    ) -> None:
        self._rag_service = rag_service
        self._conversation_service_provider = conversation_service_provider
        self._top_k = top_k
        self._outbox_enabled = outbox_enabled

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
            outbox_event = None
            if self._outbox_enabled:
                outbox_event = OutboxIntent(
                    event_type=MEMORY_EXTRACT_EVENT_TYPE,
                    payload={},
                )
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

            outbox_event = None
            if self._outbox_enabled:
                outbox_event = OutboxIntent(
                    event_type=MEMORY_EXTRACT_EVENT_TYPE,
                    payload={
                        "conversation_id": conversation_id,
                    },
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
        # Generation runs outside any transaction.
        try:
            generated = self._generate(message)
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
        )

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

    def _generate(self, message: str) -> Dict[str, Any]:
        return self._rag_service.generate_answer(message, top_k=self._top_k)
