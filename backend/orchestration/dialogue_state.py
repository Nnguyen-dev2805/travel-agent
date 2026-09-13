"""Ephemeral dialogue state for the current turn.

`DialogueState` is reconstructed from recent turns and discarded; it is not a
second durable store (`spec:269-270`). `spec:907` scopes Stage 1 to recent turns
only, so the resolver reconstructs structural facts and infers no topic, goal, or
referent — those become governed inputs when Working Memory exists in Stage 5
(`spec:265-267`).

Pure and deterministic: no model call, no database write, no Working Memory
dependency (`plan:355`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.conversations.models import Message, MessageRole, MessageStatus

#: The roles that form dialogue. `TOOL` and `SYSTEM_EVENT` rows are records
#: about the turn, not part of the exchange.
_DELIVERED_ROLES = frozenset({MessageRole.USER, MessageRole.ASSISTANT})


@dataclass(frozen=True)
class DialogueState:
    """What recent turns establish about the current turn.

    `turns` holds the delivered turns ordered by `sequence`. `latest_assistant_turn`
    is `None` when nothing has been answered yet, which is exactly the condition a
    context-dependent follow-up such as "tiếp tục đi" has nothing to resolve
    against.
    """

    turns: tuple[Message, ...]
    latest_user_turn: Message | None
    latest_assistant_turn: Message | None


class DialogueStateResolver:
    """Derive `DialogueState` from recent turns."""

    def resolve(self, recent_turns: Sequence[Message]) -> DialogueState:
        """Return the state established by `recent_turns`.

        Only `COMPLETE` user/assistant rows are turns. A `COMPLETE` row is the
        only one guaranteed to carry content — `conversations/models.py:278-285`
        requires it there and merely permits a string elsewhere — and the writer
        empties the rest: `ConversationRepository.fail_turn`
        (`conversations/postgres_repository.py:791-805`) stores `content=""`, and
        a `PENDING` row is an in-flight placeholder, which on a first turn is an
        empty assistant row. Neither can contribute dialogue state.

        Order comes from `sequence`, never from the caller's list order: the field
        is a stored monotonic integer precisely so turn order is a fact
        (`conversations/models.py:429-431`).

        Precondition: `recent_turns` are rows of **one** conversation. The
        signature carries no conversation identity (`plan:340`), so rows mixed
        across conversations would yield a plausible but meaningless state.
        """
        turns = tuple(
            sorted(
                (
                    turn
                    for turn in recent_turns
                    if turn.status is MessageStatus.COMPLETE
                    and turn.role in _DELIVERED_ROLES
                ),
                key=lambda turn: turn.sequence,
            )
        )
        return DialogueState(
            turns=turns,
            latest_user_turn=next(
                (turn for turn in reversed(turns) if turn.role is MessageRole.USER),
                None,
            ),
            latest_assistant_turn=next(
                (
                    turn
                    for turn in reversed(turns)
                    if turn.role is MessageRole.ASSISTANT
                ),
                None,
            ),
        )
