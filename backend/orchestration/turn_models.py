"""Closed turn contracts for the bounded one-turn workflow.

This module is the **single contract owner** for the Task 3 and Task 4
orchestration types (`plan v0.7:407-411`): the disposition matrix, the
understanding result, the explicit-intent decision, the context plan, and the
closed interaction/routing/context vocabularies. Behaviour lives in
`turn_understanding.py`, `action_router.py`, and `context_planner.py`; do not
create a parallel model module for the same contracts.

`TurnDisposition` names what a bounded agentic turn achieved. It is a reasoning
outcome, deliberately distinct from `MessageStatus`, which describes persistence
completeness (ADR 0023). The two are orthogonal with constrained valid
combinations (`spec:332-363`), and the disposition stays internal to `TurnOutcome`
in the first rollout rather than becoming a public Chat field (`spec:360-363`).

Contracts only: no storage, no model call, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass
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


# ---------------------------------------------------------------------------
# Task 4: closed vocabularies for understanding, routing, and context planning.
# ---------------------------------------------------------------------------


class InteractionMode(str, Enum):
    """What the current message is doing (`spec:306-308`).

    Six values, closed. `AMBIGUOUS` is a first-class outcome rather than a
    failure: the resolution order ends in deterministic escalation, and a message
    that cannot be resolved deterministically must not be guessed into an action.
    """

    NORMAL_QUERY = "normal_query"
    EXPLICIT_REMEMBER = "explicit_remember"
    EXPLICIT_CORRECT = "explicit_correct"
    EXPLICIT_FORGET = "explicit_forget"
    EXPLICIT_INSPECT = "explicit_inspect"
    AMBIGUOUS = "ambiguous"


class RoutingDecision(str, Enum):
    """Which branch one bounded turn takes (`spec:370-372`).

    `ActionRouter` is pure application logic; this vocabulary is the whole of its
    output. It is deliberately not the same enum as `InteractionMode`: several
    interaction modes route to the same branch, and the branch is what the
    orchestrator acts on.
    """

    NORMAL_QUERY = "normal_query"
    EXPLICIT_MEMORY_ACTION = "explicit_memory_action"
    NEEDS_CLARIFICATION = "needs_clarification"


class ContextMode(str, Enum):
    """The context source plan for one turn (`ADR 0039:54-66`).

    The vocabulary is complete from Stage 1, but only `NONE` and `RAG_ONLY` are
    reachable: `MEMORY_ONLY` and `BOTH` require governed Memory Read, which does
    not exist yet. Stage 1 exposes the values without making them achievable.
    """

    NONE = "none"
    RAG_ONLY = "rag_only"
    MEMORY_ONLY = "memory_only"
    BOTH = "both"


class UnderstandingReason(str, Enum):
    """Closed reason codes for an understanding or gate decision.

    Free text cannot become a reason code: the vocabulary is the control that
    keeps a log line or a model's prose out of the decision record. Every value
    names a deterministic cause, so a reader can tell why a turn routed where it
    did without replaying the classifier.
    """

    NO_EXPLICIT_SIGNAL = "no_explicit_signal"
    DETERMINISTIC_MATCH = "deterministic_match"
    QUOTED_SPEECH_ACT = "quoted_speech_act"
    NEGATED_SPEECH_ACT = "negated_speech_act"
    AMBIGUOUS_SPEECH_ACT = "ambiguous_speech_act"
    #: A memory cue appeared inside a question or a definition request, so it is a
    #: mention of the word rather than the user issuing a command. Distinct from
    #: `NO_EXPLICIT_SIGNAL` because the cue *was* present and the reading must be
    #: diagnosable as a deliberate refusal rather than an absence.
    MENTION_NOT_SPEECH_ACT = "mention_not_speech_act"
    CONTEXT_REQUIRED = "context_required"
    CONTEXT_MISSING = "context_missing"
    INSPECT_CAPABILITY_UNAVAILABLE = "inspect_capability_unavailable"
    PARSER_FAILED_CLOSED = "parser_failed_closed"


#: The modes that propose a durable Memory mutation. Only these require the
#: `ExplicitIntentGate` corroboration (`ADR 0036:34-41`); `EXPLICIT_INSPECT` is
#: read-only and `NORMAL_QUERY`/`AMBIGUOUS` propose nothing.
DURABLE_ACTION_MODES: frozenset[InteractionMode] = frozenset(
    {
        InteractionMode.EXPLICIT_REMEMBER,
        InteractionMode.EXPLICIT_CORRECT,
        InteractionMode.EXPLICIT_FORGET,
    }
)


@dataclass(frozen=True)
class TurnUnderstandingResult:
    """The governed semantic reading of the current message (`spec:303-317`).

    Every field is a claim about meaning, so the defaults are the empty claim:
    an ordinary query asserts nothing. `reason_codes` is closed, and
    `needs_clarification` is the deterministic escape when the message cannot be
    resolved — never a silent guess.

    `current_goal` and `answers_pending_clarification` are the two
    dialogue-state semantics `plan v0.7:400-403` requires this layer to derive.
    They are read out of the structural state (what the last user turn asked for,
    whether the last assistant turn asked something), so nothing semantic has to
    live in `DialogueState`.
    """

    interaction_mode: InteractionMode
    topics: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    current_assertions: tuple[str, ...] = ()
    current_overrides: tuple[str, ...] = ()
    memory_namespaces_needed: tuple[str, ...] = ()
    temporal_context: str | None = None
    needs_clarification: bool = False
    reason_codes: tuple[UnderstandingReason, ...] = ()
    current_goal: str | None = None
    answers_pending_clarification: bool = False


@dataclass(frozen=True)
class ExplicitIntentDecision:
    """Whether the speech act is corroborated well enough to mutate durably.

    `ExplicitIntentGate` produces this; it is an authorization boundary, not a
    second extractor (`ADR 0036:34-41`). There is no tri-state: a caller cannot
    read "unset" as permission, which is the fail-closed shape the gate needs.
    """

    authorized: bool
    reason_code: UnderstandingReason


@dataclass(frozen=True)
class ContextPlan:
    """The proposed context source plan and the one that will actually execute.

    The two are separate fields on purpose (`plan v0.7:444-450`). While
    `CONTEXT_PLANNER_ENFORCEMENT_ENABLED` is false the planner still proposes, but
    the effective normal-query mode stays the existing `RAG_ONLY` baseline, so a
    proposal of `NONE` cannot silently skip retrieval. `is_shadow` is exactly
    "the proposal was not adopted", which is the evidence Stage 1 collects.
    """

    proposed: ContextMode
    effective: ContextMode

    @property
    def is_shadow(self) -> bool:
        """`True` when the proposal was not adopted for execution."""
        return self.proposed is not self.effective
