"""Positive family-specific source handling: proposal, record, and the gate.

Background Memory must not infer permission from absence (`ADR 0038:59`). This
module is the whole of that rule, expressed as three separate things so that a
later stage cannot collapse them:

- `SourceHandlingProposal` — typed evidence that *this turn* was considered.
  Orchestration produces it from what it already knows. It carries no storage
  identity and grants nothing. A blocked proposal is a recorded refusal, not a
  pending decision.
- `SourceHandlingRecord` — the durable authority object, keyed by
  `(source_outbox_id, family)`. Only the Stage-2 persistence seam may create
  one, because only that seam knows the outbox identity (`spec:484-490`).
- `allows_background_formation` — the single predicate that turns a record into
  permission. It answers `True` for exactly one outcome and `False` for
  everything else, including `None`.

`UNHANDLED` is deliberately **not** a member of `SourceHandlingOutcome`. It is
the semantic state created by the *absence* of a record, so it is represented by
the predicate's `None` branch rather than by a value that could be written down
and later compared. Making it a member would give absence a name, and a name is
the first step towards treating it as a state that can be checked for
permission.

`BACKGROUND_BLOCKED` is likewise proposal-only: the authoritative vocabulary has
no such member, so a blocked proposal cannot be persisted as a decision.

`SENSITIVE_BLOCKED` is part of the closed reason vocabulary and the mapping
below covers it, but Stage 1 orchestration does not emit it. Secret detection is
owned by the write pipeline, and reaching into it from here would both invert
the dependency direction and duplicate the ownership. The reason exists so that
the mapping is total, and so the stage that legitimately detects prohibited
content has a governed way to report it. Later formation still revalidates
prohibited content before any model use.

Standard library only. This module is imported by orchestration, so importing
`backend.memory.write_pipeline` from here would execute that package's
`__init__`, which pulls `backend.security`, which pulls FastAPI — putting a web
framework into a domain module's import graph. The vocabulary lives at the
`backend.memory` root for that reason.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class MemoryFamily(str, Enum):
    """The closed set of Memory families (`spec:244-254`).

    One vocabulary for the whole architecture, defined here because source
    handling is the first thing that has to name a family. Task 6 reuses it
    rather than declaring a parallel enum.
    """

    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    WORKING = "working"
    PROCEDURAL = "procedural"


class SourceHandlingProposalOutcome(str, Enum):
    """What a turn's source handling proposes. Two values, both non-binding."""

    BACKGROUND_ELIGIBLE = "background_eligible"
    BACKGROUND_BLOCKED = "background_blocked"


class SourceHandlingReason(str, Enum):
    """Why a source was handled the way it was.

    Closed on purpose: a log line, a model's prose, or an exception message must
    not be able to become a reason. Observability may project `.value` into its
    bounded `reason_code`; nothing in persistence or domain logic branches on
    free text.
    """

    EXPLICIT_ACTION = "explicit_action"
    BACKGROUND_POLICY_ELIGIBLE = "background_policy_eligible"
    AMBIGUOUS_INTENT = "ambiguous_intent"
    SENSITIVE_BLOCKED = "sensitive_blocked"


class SourceHandlingOutcome(str, Enum):
    """The authoritative outcomes a persisted record may carry (`spec:466-473`).

    One positive outcome and five that describe an explicit handling. Note the
    absence of `BACKGROUND_BLOCKED`: a refusal is a property of a proposal,
    never of a durable decision.
    """

    BACKGROUND_ELIGIBLE = "background_eligible"
    EXPLICIT_APPLIED = "explicit_applied"
    EXPLICIT_REFUSED = "explicit_refused"
    EXPLICIT_NOOP = "explicit_noop"
    FORGET_APPLIED = "forget_applied"
    FORGET_REFUSED = "forget_refused"


#: The closed reason -> proposal-outcome mapping (`spec:440-445`), written once.
#: A caller states a reason and the outcome follows, so the two fields can never
#: disagree in the proposal Stage 2 later binds to an outbox row.
_PROPOSAL_OUTCOME_BY_REASON: dict[SourceHandlingReason, SourceHandlingProposalOutcome] = {
    SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE: (
        SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE
    ),
    SourceHandlingReason.EXPLICIT_ACTION: (
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED
    ),
    SourceHandlingReason.AMBIGUOUS_INTENT: (
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED
    ),
    SourceHandlingReason.SENSITIVE_BLOCKED: (
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED
    ),
}

#: Families a proposal may be made for. The other values are canonical
#: vocabulary that becomes operational only in the stage that evaluates that
#: family's formation behaviour.
#:
#: `EPISODIC` joined at the Stage-5 slice (plan v0.20 Task 12) and `WORKING` at
#: the Stage-5 Working Memory slice (plan v0.22 Task 13) — each in the stage that
#: evaluates that family's formation, which is the same rule that admitted
#: `SEMANTIC` in Stage 1. `PROCEDURAL` stays out until its own stage, so a caller
#: cannot obtain background permission for a family whose formation rules nobody
#: has written yet.
STAGE_ONE_PROPOSABLE_FAMILIES: frozenset[MemoryFamily] = frozenset(
    {
        MemoryFamily.SEMANTIC,
        MemoryFamily.EPISODIC,
        MemoryFamily.WORKING,
    }
)


def _coerce_family(value: Any) -> MemoryFamily:
    if isinstance(value, MemoryFamily):
        return value
    if isinstance(value, str):
        try:
            return MemoryFamily(value)
        except ValueError as error:
            raise ValueError("Unknown MemoryFamily value.") from error
    raise ValueError("Field 'family' must be a MemoryFamily value.")


def _coerce_proposal_outcome(value: Any) -> SourceHandlingProposalOutcome:
    if isinstance(value, SourceHandlingProposalOutcome):
        return value
    if isinstance(value, str):
        try:
            return SourceHandlingProposalOutcome(value)
        except ValueError as error:
            raise ValueError(
                "Unknown SourceHandlingProposalOutcome value."
            ) from error
    raise ValueError("Field 'outcome' must be a SourceHandlingProposalOutcome value.")


def _coerce_record_outcome(value: Any) -> SourceHandlingOutcome:
    if isinstance(value, SourceHandlingOutcome):
        return value
    if isinstance(value, str):
        try:
            return SourceHandlingOutcome(value)
        except ValueError as error:
            raise ValueError("Unknown SourceHandlingOutcome value.") from error
    raise ValueError("Field 'outcome' must be a SourceHandlingOutcome value.")


def _coerce_reason(value: Any) -> SourceHandlingReason:
    if isinstance(value, SourceHandlingReason):
        return value
    if isinstance(value, str):
        try:
            return SourceHandlingReason(value)
        except ValueError as error:
            raise ValueError("Unknown SourceHandlingReason value.") from error
    raise ValueError("Field 'reason_code' must be a SourceHandlingReason value.")


def _require_identity(value: Any, field: str) -> str:
    """Identities are the uniqueness boundary, so a blank one is not one."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field}' must be a non-empty identifier.")
    return value


def _require_utc(value: Any, field: str) -> datetime:
    """A durable record's time must be unambiguous and stored as UTC.

    The same contract the existing durable Memory domain applies
    (`write_pipeline/models.py:156-161`). It matters more here than it looks: a
    naive value would be persisted as whatever the writing host's local time
    happened to be, so two records written by two hosts could not be ordered
    against each other. Normalising rather than merely validating means equality
    and ordering do not depend on the offset the writer used.
    """
    if not isinstance(value, datetime):
        raise ValueError(f"Field '{field}' must be a datetime.")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"Field '{field}' must carry timezone information.")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SourceHandlingProposal:
    """Non-authoritative evidence that one turn's source was considered.

    No `source_outbox_id` and no `recorded_at`: storage identity belongs to the
    Stage-2 seam, and a proposal is not a durable fact with a time.
    """

    source_message_id: str
    family: MemoryFamily
    outcome: SourceHandlingProposalOutcome
    reason_code: SourceHandlingReason

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_message_id",
            _require_identity(self.source_message_id, "source_message_id"),
        )
        object.__setattr__(self, "family", _coerce_family(self.family))

        # The mapping is enforced here and not only in the factory below. The
        # dataclass is public, so without this a caller can build
        # `BACKGROUND_ELIGIBLE` + `EXPLICIT_ACTION` by hand: a proposal that
        # reads as "safe to infer from" while naming the reason that says the
        # source was already handled explicitly. Stage 2 binds proposals to
        # outbox rows, so a contradictory one would reach storage.
        reason = _coerce_reason(self.reason_code)
        outcome = _coerce_proposal_outcome(self.outcome)
        expected = _PROPOSAL_OUTCOME_BY_REASON[reason]
        if outcome is not expected:
            raise ValueError(
                f"Proposal outcome '{outcome.value}' contradicts reason "
                f"'{reason.value}'; the closed mapping requires "
                f"'{expected.value}'."
            )
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "reason_code", reason)


@dataclass(frozen=True)
class SourceHandlingRecord:
    """The authoritative, durable source-handling decision.

    The uniqueness boundary is `(source_outbox_id, family)`: one source event
    may be handled once per family, because each family's formation is a
    separate consumer of that event.
    """

    source_outbox_id: str
    source_message_id: str
    family: MemoryFamily
    outcome: SourceHandlingOutcome
    reason_code: SourceHandlingReason
    recorded_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_outbox_id",
            _require_identity(self.source_outbox_id, "source_outbox_id"),
        )
        object.__setattr__(
            self,
            "source_message_id",
            _require_identity(self.source_message_id, "source_message_id"),
        )
        object.__setattr__(self, "family", _coerce_family(self.family))
        object.__setattr__(self, "outcome", _coerce_record_outcome(self.outcome))
        object.__setattr__(self, "reason_code", _coerce_reason(self.reason_code))
        object.__setattr__(
            self, "recorded_at", _require_utc(self.recorded_at, "recorded_at")
        )


def propose_source_handling(
    *,
    source_message_id: str,
    family: MemoryFamily | str,
    reason_code: SourceHandlingReason | str,
) -> SourceHandlingProposal:
    """Derive the Stage-1 proposal for one turn's source.

    The caller states the *reason* and this function derives the outcome, so a
    call site cannot assert an outcome that contradicts the reason it gave.

    Refuses a family Stage 1 may not propose for. It raises rather than
    downgrading to `BACKGROUND_BLOCKED` because a downgrade would have to keep a
    reason that no longer matches its outcome, and the closed mapping above
    forbids exactly that pair.
    """
    resolved_family = _coerce_family(family)
    if resolved_family not in STAGE_ONE_PROPOSABLE_FAMILIES:
        raise ValueError(
            f"Stage 1 may not propose background handling for the "
            f"'{resolved_family.value}' family; it becomes proposable only in "
            f"the stage that evaluates that family."
        )

    resolved_reason = _coerce_reason(reason_code)
    return SourceHandlingProposal(
        source_message_id=source_message_id,
        family=resolved_family,
        outcome=_PROPOSAL_OUTCOME_BY_REASON[resolved_reason],
        reason_code=resolved_reason,
    )


def allows_background_formation(record: SourceHandlingRecord | None) -> bool:
    """Whether a persisted record grants background formation for its family.

    This is the only authority boundary in the module, and it is deliberately
    narrow: a real record whose outcome is exactly `BACKGROUND_ELIGIBLE`. Every
    other input denies, including `None` — which is `UNHANDLED`, the state this
    rule exists to stop treating as permission.

    The check is on the type and the enum member, not on a string value. A
    duck-typed object carrying `"background_eligible"` is not a decision.
    """
    if not isinstance(record, SourceHandlingRecord):
        return False
    return record.outcome is SourceHandlingOutcome.BACKGROUND_ELIGIBLE


def authority_key(record: SourceHandlingRecord) -> tuple[str, MemoryFamily]:
    """The durable uniqueness boundary of one record (`spec:479-482`).

    Exposed as a function so the storage seam keys on it without re-deriving the
    tuple from field order in two places.
    """
    return (record.source_outbox_id, record.family)
