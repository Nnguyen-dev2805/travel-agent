"""Conversation orchestration seam for runtime milestone R4.

Per ADR 0005 this module owns coordination between conversation persistence and
RAG generation for one chat turn. The chat route delegates rather than
orchestrating, and `backend/rag` stays unaware that conversations exist.

Turn ordering and the partial-failure policy live here:

1. A bound turn persists the user message **before** any model call, so a caller
   is never charged for an unrecorded turn.
2. Generation runs unchanged.
3. The assistant turn is persisted afterwards. If that write fails, the reply is
   still returned with `persisted` `False`, so a persistence gap is visible
   rather than silent.

`RAGService` and `ConversationService` are injected rather than imported at
runtime. Importing the RAG facade would pull the vector-store client into every
module that touches a chat turn, and importing the conversation service eagerly
would construct local storage for unbound turns that need none.

Message content passes through this module and is never logged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from backend.conversations.models import MessageRole, MessageSource
from backend.conversations.repository import ConversationRepositoryError

if TYPE_CHECKING:  # pragma: no cover - typing only, never imported at runtime
    from backend.conversations.service import ConversationService

logger = logging.getLogger("travel_agent_orchestration")

DEFAULT_TOP_K = 4
"""Retrieval breadth for one chat turn.

Declared here rather than imported from `backend.rag.generation` so the
orchestration seam carries no runtime dependency on the vector-store client. It
mirrors the value the chat route has always passed, which the unbound chat
compatibility test pins.
"""


@dataclass(frozen=True)
class TurnPersistence:
    """What a bound turn managed to persist.

    `persisted` is `False` with `assistant_message_id` absent when the assistant
    write failed after a successful generation.
    """

    conversation_id: str
    user_message_id: Optional[str]
    assistant_message_id: Optional[str]
    persisted: bool


@dataclass(frozen=True)
class TurnOutcome:
    """The result of one chat turn.

    `conversation` is `None` for an unbound turn, which is what keeps the
    existing chat response byte-for-byte unchanged for a caller that does not
    opt in.
    """

    reply: str
    model: str
    citations: List[Dict[str, Any]]
    conversation: Optional[TurnPersistence] = None


class ConversationOrchestrator:
    """Coordinate conversation persistence and RAG generation for one turn."""

    def __init__(
        self,
        rag_service: Any,
        conversation_service_provider: Callable[[], "ConversationService"],
        top_k: int = DEFAULT_TOP_K,
    ) -> None:
        self._rag_service = rag_service
        self._conversation_service_provider = conversation_service_provider
        self._top_k = top_k

    def handle_turn(
        self, message: str, conversation_id: Optional[str] = None
    ) -> TurnOutcome:
        """Run one chat turn, persisting it when the caller supplied a conversation.

        Raises:
            ConversationNotFoundError: A `conversation_id` was supplied but no
                such conversation exists. No model call is made.
            ConversationRepositoryError: The user turn could not be persisted. No
                model call is made.
            Exception: Generation failures propagate unchanged, and an already
                persisted user turn survives as provenance.
        """
        if conversation_id is None:
            return self._unbound_turn(message)

        conversations = self._conversation_service_provider()

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
        )

    def _unbound_turn(self, message: str) -> TurnOutcome:
        generated = self._generate(message)
        return TurnOutcome(
            reply=generated["reply"],
            model=generated["model"],
            citations=generated["citations"],
            conversation=None,
        )

    def _generate(self, message: str) -> Dict[str, Any]:
        return self._rag_service.generate_answer(message, top_k=self._top_k)
