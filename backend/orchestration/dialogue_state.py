"""Ephemeral dialogue state for the current turn.

`DialogueState` is reconstructed from recent turns and discarded; it is not a
second durable store (`spec:284-285`).

Stage-1 responsibility is deliberately **structural** (`plan:343-348`,
`spec:265-270`): retain the eligible delivered user/assistant turns of exactly
one conversation, order them by stored `sequence`, and expose the latest user and
assistant turns. This module infers **no** topic, referent, current goal, intent,
or clarification semantics — `TurnUnderstanding` owns semantic interpretation of
the current message against this state (Task 4, `spec:272-275`).

Once Working Memory exists in Stage 5 it becomes an additional input to this
reconstruction, which "does not transfer semantic-interpretation ownership out of
`TurnUnderstanding`" (`spec:279-281`).

Pure and deterministic: no model call, no database write, no Working Memory
dependency (`plan:364-365`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from backend.conversations.models import (
    ConversationValidationError,
    Message,
    MessageRole,
    MessageStatus,
)

#: The roles that form dialogue. `TOOL` and `SYSTEM_EVENT` rows are records
#: about the turn, not part of the exchange.
_DELIVERED_ROLES = frozenset({MessageRole.USER, MessageRole.ASSISTANT})


@dataclass(frozen=True)
class DialogueState:
    """The structural dialogue context of exactly one conversation.

    `turns` holds the delivered turns ordered by `sequence`. `latest_assistant_turn`
    is `None` while no delivered assistant turn exists — the structural condition
    that tells `TurnUnderstanding` there is nothing yet to build on. Whether a
    message such as "tiếp tục đi" actually refers back to it is a semantic question
    this contract deliberately does not answer (`spec:272-275`).
    """

    turns: tuple[Message, ...]
    latest_user_turn: Message | None
    latest_assistant_turn: Message | None


class DialogueStateResolver:
    """Assemble structural `DialogueState` from the recent turns of one conversation."""

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

        The rows must belong to exactly **one** conversation. The signature
        carries no conversation identity (`plan:340`), so the rows are the only
        evidence of scope, and rows from more than one conversation fail closed
        (`spec:268-269`) instead of producing a plausible cross-conversation
        state. Scope is decided on the rows **supplied**, not on the rows
        retained: a foreign row is a foreign row even when the eligibility filter
        would have dropped it.
        """
        # Materialize before the scope check. Reading the iterable twice would
        # drain a one-shot iterable in the guard, and the filter below would then
        # see nothing and return an empty state — failing open inside the guard
        # whose whole purpose is to fail closed.
        rows = tuple(recent_turns)

        supplied_conversations = {turn.conversation_id for turn in rows}
        if len(supplied_conversations) > 1:
            raise ConversationValidationError(
                "Dialogue state requires rows from exactly one conversation; "
                f"{len(supplied_conversations)} were supplied."
            )
        turns = tuple(
            sorted(
                (
                    turn
                    for turn in rows
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
