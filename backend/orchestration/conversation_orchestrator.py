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

from backend.conversations.models import MessageRole, MessageSource, OutboxIntent
from backend.conversations.repository import ConversationRepositoryError
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
        if conversation_id is None:
            return self._unbound_turn(message)

        conversations = self._conversation_service_provider()

        conversation = conversations.get_conversation(conversation_id)
        if conversation is None:
            if principal is not None and getattr(principal, "auth_mode", None) == "authenticated":
                from backend.security.models import CrossOwnerAccessError
                raise CrossOwnerAccessError(
                    "The conversation does not exist in this owner scope."
                )
            from backend.conversations.service import ConversationNotFoundError
            raise ConversationNotFoundError("The conversation does not exist.")

        if principal is not None and getattr(principal, "auth_mode", None) == "authenticated":
            from backend.security.models import CrossOwnerAccessError
            conv_owner = getattr(conversation, "owner_user_id", None)
            if conv_owner != principal.owner_user_id:
                raise CrossOwnerAccessError(
                    "The conversation does not exist in this owner scope."
                )

        outbox_event = None
        if self._outbox_enabled:
            outbox_event = OutboxIntent(
                event_type="memory.extract.conversation_range",
                payload={
                    "conversation_id": conversation_id,
                },
            )

        if outbox_event is not None:
            user_message = conversations.append_message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=message,
                source=MessageSource.UI,
                outbox_event=outbox_event,
            )
        else:
            user_message = conversations.append_message(
                conversation_id=conversation_id,
                role=MessageRole.USER,
                content=message,
                source=MessageSource.UI,
            )

        generated = self._generate(message)

        try:
            assistant_message = conversations.append_message(
                conversation_id=conversation_id,
                role=MessageRole.ASSISTANT,
                content=generated["reply"],
                source=MessageSource.MODEL,
            )
        except ConversationRepositoryError as error:
            logger.error(
                "chat.turn persistence_degraded conversation_id=%s "
                "user_message_id=%s stage=assistant_message failure_class=%s",
                conversation_id,
                user_message.message_id,
                type(error).__name__,
            )
            return TurnOutcome(
                reply=generated["reply"],
                model=generated["model"],
                citations=generated["citations"],
                conversation=TurnPersistence(
                    conversation_id=conversation_id,
                    user_message_id=user_message.message_id,
                    assistant_message_id=None,
                    persisted=False,
                ),
                memory=None,
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

    def _unbound_turn(self, message: str) -> TurnOutcome:
        generated = self._generate(message)
        return TurnOutcome(
            reply=generated["reply"],
            model=generated["model"],
            citations=generated["citations"],
            conversation=None,
            memory=None,
        )

    def _generate(self, message: str) -> Dict[str, Any]:
        return self._rag_service.generate_answer(message, top_k=self._top_k)
