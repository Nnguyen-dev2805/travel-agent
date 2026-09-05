"""Conversation orchestration seam for runtime milestones R4 through R6.

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

Per ADR 0007, R6 adds feature-gated memory retrieval to the bound path only.
When the gate is disabled, or the turn is unbound, generation follows the R4
path exactly and no memory storage is resolved. When enabled for a bound turn,
the orchestrator selects in-scope active memories, prepends a controlled
memory section to travel RAG context through the injectable RAG seam, and
reports selected memory IDs and reasons. A memory retrieval failure degrades
to an ungated answer with a `skipped` trace rather than failing the turn.

`RAGService` and `ConversationService` are injected rather than imported at
runtime. Importing the RAG facade would pull the vector-store client into every
module that touches a chat turn, and importing the conversation service eagerly
would construct local storage for unbound turns that need none. The memory
retrieval components arrive behind a provider for the same reason: resolving
them eagerly would open the memory database even for turns that never use it.

Message content passes through this module and is never logged.
"""

from __future__ import annotations

import dataclasses
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

from backend.conversations.models import MessageRole, MessageSource
from backend.conversations.repository import ConversationRepositoryError
from backend.memory.models import MemorySelectionStatus
from backend.memory.repository import MemoryRepositoryError
from backend.orchestration.memory_context import compose_memory_section

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
class TurnMemory:
    """What feature-gated memory retrieval decided for one bound turn.

    `None` on the outcome means memory was not in play at all: the turn was
    unbound or the gate was disabled. A present value carries controlled
    identifiers and reasons only, never memory text.
    """

    enabled: bool
    status: str
    selected_memory_ids: Tuple[str, ...]
    selection_reasons: Tuple[str, ...]


@dataclass(frozen=True)
class TurnOutcome:
    """The result of one chat turn.

    `conversation` is `None` for an unbound turn, which is what keeps the
    existing chat response byte-for-byte unchanged for a caller that does not
    opt in. `memory` is `None` unless the feature gate was enabled for a
    bound turn.
    """

    reply: str
    model: str
    citations: List[Dict[str, Any]]
    conversation: Optional[TurnPersistence] = None
    memory: Optional[TurnMemory] = None


class ConversationOrchestrator:
    """Coordinate conversation persistence and RAG generation for one turn."""

    def __init__(
        self,
        rag_service: Any,
        conversation_service_provider: Callable[[], "ConversationService"],
        top_k: int = DEFAULT_TOP_K,
        memory_enabled: bool = False,
        memory_provider: Optional[Callable[[], Tuple[Any, Any]]] = None,
        max_selected: int = 5,
    ) -> None:
        self._rag_service = rag_service
        self._conversation_service_provider = conversation_service_provider
        self._top_k = top_k
        self._memory_enabled = memory_enabled
        self._memory_provider = memory_provider
        self._max_selected = max_selected

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

        if self._memory_enabled:
            generated, turn_memory = self._generate_with_memory(
                message, conversations, conversation_id
            )
        else:
            generated = self._generate(message)
            turn_memory = None

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
                memory=turn_memory,
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
            memory=turn_memory,
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

    def _generate_with_memory(
        self, message: str, conversations: Any, conversation_id: str
    ) -> Tuple[Dict[str, Any], TurnMemory]:
        """Generate one bound turn with feature-gated memory selection.

        Memory retrieval failure degrades to an ungated answer with a
        `skipped` trace rather than failing the turn: memory is an answer
        enhancement, and the gap stays visible in the trace instead of
        silent.
        """
        try:
            selections = self._select_memories(message, conversations, conversation_id)
        except (MemoryRepositoryError, ConversationRepositoryError) as error:
            logger.error(
                "chat.turn memory_skipped conversation_id=%s failure_class=%s",
                conversation_id,
                type(error).__name__,
            )
            return self._generate(message), TurnMemory(
                enabled=True,
                status=MemorySelectionStatus.SKIPPED.value,
                selected_memory_ids=(),
                selection_reasons=(),
            )

        section = compose_memory_section(selections)
        if not section:
            return self._generate(message), TurnMemory(
                enabled=True,
                status=MemorySelectionStatus.NONE_SELECTED.value,
                selected_memory_ids=(),
                selection_reasons=(),
            )

        bundle = self._rag_service.build_travel_context(message, top_k=self._top_k)
        composed = dataclasses.replace(
            bundle, prompt_context=f"{section}\n\n{bundle.prompt_context}"
        )
        generated = self._rag_service.generate_from_context(message, composed)
        logger.info(
            "chat.turn memory_selected conversation_id=%s count=%s",
            conversation_id,
            len(selections),
        )
        return generated, TurnMemory(
            enabled=True,
            status=MemorySelectionStatus.SELECTED.value,
            selected_memory_ids=tuple(selection.memory_id for selection in selections),
            selection_reasons=tuple(selection.reason.value for selection in selections),
        )

    def _select_memories(
        self, message: str, conversations: Any, conversation_id: str
    ) -> Tuple[Any, ...]:
        if self._memory_provider is None:
            raise MemoryRepositoryError(
                "Memory retrieval is enabled without a memory provider."
            )
        components = self._memory_provider()
        if components is None:
            raise MemoryRepositoryError(
                "Memory retrieval components could not be resolved."
            )
        retrieval_service, resolve_owner = components
        conversation = conversations.get_conversation(conversation_id)
        if conversation is None:  # pragma: no cover - just persisted above
            raise MemoryRepositoryError(
                "Memory retrieval could not resolve its conversation."
            )
        owner_user_id = resolve_owner(conversation.workspace_id)
        if owner_user_id is None:
            raise MemoryRepositoryError(
                "Memory retrieval could not resolve its workspace scope."
            )
        return retrieval_service.select_memories(
            owner_user_id=owner_user_id,
            workspace_id=conversation.workspace_id,
            conversation_id=conversation_id,
            query=message,
            max_selected=self._max_selected,
        )
