"""Closed turn contracts for the bounded one-turn workflow.

`TurnDisposition` names what a bounded agentic turn achieved. It is a reasoning
outcome, deliberately distinct from `MessageStatus`, which describes persistence
completeness (ADR 0023). The two are orthogonal with constrained valid
combinations (`spec:332-363`), and the disposition stays internal to `TurnOutcome`
in the first rollout rather than becoming a public Chat field (`spec:360-363`).

Contracts only: no storage, no model call, no I/O.
"""

from __future__ import annotations

from enum import Enum

from backend.conversations.models import MessageStatus


class TurnDisposition(str, Enum):
    """What the bounded turn achieved (`spec:336-344`).

    `EXECUTION_FAILED` is not a persistence failure: a `COMPLETE` row carrying it
    reports an execution or context limitation, and the reply itself was stored
    (`spec:355-358`).
    """

    ANSWERED = "answered"
    NEEDS_CLARIFICATION = "needs_clarification"
    INCOMPLETE = "incomplete"
    EXECUTION_FAILED = "execution_failed"


#: The approved matrix (`spec:352-356`), written once. `None` is the "not
#: finalized yet" value and is valid only while the row is still `PENDING`.
_VALID_DISPOSITIONS: dict[MessageStatus, frozenset[TurnDisposition | None]] = {
    MessageStatus.PENDING: frozenset({None}),
    MessageStatus.FAILED: frozenset(
        {
            TurnDisposition.NEEDS_CLARIFICATION,
            TurnDisposition.INCOMPLETE,
            TurnDisposition.EXECUTION_FAILED,
        }
    ),
    MessageStatus.COMPLETE: frozenset(TurnDisposition),
}


def disposition_is_valid(
    status: MessageStatus, disposition: TurnDisposition | None
) -> bool:
    """Whether one persisted status may carry one finalized disposition.

    A terminal row must carry a disposition: a `FAILED` row can never be
    `ANSWERED`, and a `COMPLETE` row accepts any of the four. An unrecognized
    status accepts nothing, so the matrix fails closed if the status vocabulary
    grows without this table being extended.
    """
    return disposition in _VALID_DISPOSITIONS.get(status, frozenset())
