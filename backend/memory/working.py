"""Working Memory vertical slice (Stage 5, plan v0.22 Task 13).

Working Memory is the durable, conversation-scoped **open state** that keeps
continuity under context limits. It is not the ephemeral `DialogueState`, which is
reconstructed per turn and discarded (`spec:330-331`), and the two are different
types for exactly that reason.

**Two formation paths, one replacement semantics** (`plan v0.22` Task 13):

- a **deterministic synchronous transition** derives open state that is certain
  from governed conversation state and runs no summarization model;
- the **worker** forms an inferred replacement over a bounded completed source
  range, and needs a persisted
  `SourceHandlingRecord(family=WORKING, outcome=BACKGROUND_ELIGIBLE)` before it may
  do any work at all.

Both write through `WorkingReplacementPolicy` and the same canonical row. Two
canonical writers with different meanings is the failure mode this avoids, so the
paths differ only in how a candidate is derived.

**Why the background path runs no model.** `ADR 0038:83-84` gives Working
activation two inputs — "governed deterministic conversation transition" and
"validated source-consistent replacement" — and `spec:1037` says the inferred row
is "summary/open-state replacement after **source-consistency checks**". Both are
deterministic. A summarization model would be a new model contract with its own
prompt and schema versions, and inventing one before the family's evaluation says
what a Working state must contain is the speculative modelling this plan forbids.
The authority gate still runs *before* any model exposure, and that ordering is
what the slice proves.

**Why the open state is only a goal and a cursor.** `spec:298` lists summary, open
goal, temporary override and unresolved question as representative Working types.
This slice models the goal and the source cursor, and deliberately nothing else:
`event` is a bounded string in the episodic family for the same reason — a closed
ontology invented before the evaluation says which types matter is exactly what
`plan` refuses. The goal rule is this module's own bounded deterministic rule; it
does not re-interpret language and it does not move interpretation ownership out of
`TurnUnderstanding`, because Working state is a *supplementary* input to dialogue
reconstruction rather than the interpreter of it (`spec:324-328`).

`memory_summaries.content` is a legacy placeholder column from `20260907_02`. It is
never read here, never written here, and never policy authority — the same
treatment Task 12 gave episodic `payload`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol, Sequence

from backend.memory.lifecycle import (
    LifecycleFacts,
    LifecycleStage,
    MemoryLifecyclePolicy,
    RetentionAssignmentPolicy,
    SourceValidity,
)
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingRecord,
    allows_background_formation,
)
from backend.memory.write_pipeline.models import (
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)
from backend.memory.write_pipeline.secrets import detect_prohibited_content

#: Bounds on the open state. An open goal is a request, not a transcript: an
#: unbounded string is a raw-source channel wearing a typed field's name, and the
#: architecture keeps raw evidence out of durable instruction paths by default
#: (`spec:1079`). Over-long input is refused rather than truncated, because
#: truncating would hide the fact that something other than a goal was supplied.
MAX_GOAL_LENGTH = 1000

#: Identity bound, shared with the episodic slice's provenance bound.
MAX_IDENTITY_LENGTH = 256


class WorkingOrigin(str, Enum):
    """Which formation path produced a candidate.

    The origin is part of the candidate rather than of the caller, because
    activation depends on it: an inferred replacement is shadow until the family
    gate is conclusive, a deterministic transition is not.
    """

    DETERMINISTIC_TRANSITION = "deterministic_transition"
    INFERRED_REPLACEMENT = "inferred_replacement"


class WorkingRefusalReason(str, Enum):
    """Closed vocabulary for why an open state was refused."""

    MISSING_GOAL = "missing_goal"
    INVALID_GOAL = "invalid_goal"
    MISSING_CURSOR = "missing_cursor"
    INVALID_CURSOR = "invalid_cursor"
    MISSING_PROVENANCE = "missing_provenance"
    INVALID_PROVENANCE = "invalid_provenance"


@dataclass(frozen=True)
class WorkingProvenance:
    """Where the open state came from.

    The identity pair mirrors the source-handling authority key, so a redelivered
    or re-extracted source yields an equal provenance and can never be counted as
    independent support (`ADR 0038:90-91`).
    """

    source_outbox_id: Any
    source_message_id: Any


@dataclass(frozen=True)
class WorkingOpenState:
    """The bounded, structured open state of one conversation.

    `through_sequence` is the source cursor: the highest delivered sequence the
    state accounts for. It is the ordering fact replacement is decided on, which
    is why it is required rather than inferred from the row's write time.
    """

    open_goal: Any
    through_sequence: Any


def _is_bounded_text(value: Any, limit: int) -> bool:
    return isinstance(value, str) and 0 < len(value.strip()) <= limit


def validate_working_state(
    state: WorkingOpenState | None,
) -> WorkingRefusalReason | None:
    """Return the reason this open state is invalid, or `None` when it is usable.

    Ordered, and the order is the contract: a caller that fixes the reported
    problem and re-runs gets the next one, so a refusal is actionable rather than
    merely true. Constructing an incomplete state is allowed on purpose, so the
    refusal can be observed with its reason instead of surfacing as a
    construction-time exception the caller cannot classify.
    """
    if state is None:
        return WorkingRefusalReason.MISSING_GOAL

    goal = state.open_goal
    if goal is None or (isinstance(goal, str) and not goal.strip()):
        return WorkingRefusalReason.MISSING_GOAL
    if not _is_bounded_text(goal, MAX_GOAL_LENGTH):
        return WorkingRefusalReason.INVALID_GOAL

    cursor = state.through_sequence
    if cursor is None:
        return WorkingRefusalReason.MISSING_CURSOR
    if isinstance(cursor, bool) or not isinstance(cursor, int):
        return WorkingRefusalReason.INVALID_CURSOR
    if cursor < 1:
        # Sequence allocation starts at 1, so a zero or negative cursor is not a
        # fact any writer could have stored.
        return WorkingRefusalReason.INVALID_CURSOR
    return None


#: The delivered roles that form dialogue. `TOOL` and `SYSTEM_EVENT` rows are
#: records about the turn, not part of the exchange.
_DELIVERED_ROLES = frozenset({"user", "assistant"})


def _looks_like_question(text: str) -> bool:
    """Whether an assistant turn asked something.

    Deliberately the narrowest rule that is still honest: a trailing question
    mark. The understanding layer has a richer interrogative-marker set, and
    duplicating it here would create two rules to keep in step. Working Memory
    only needs to know whether the *immediately following* user turn is plausibly
    an answer, and being conservative here costs at most a goal that is one turn
    earlier than the understanding layer's — which is a supplementary input, not
    the interpreter.
    """
    return str(text or "").strip().endswith("?")


def derive_open_state(turns: Sequence[Any]) -> WorkingOpenState | None:
    """Derive the bounded open state from delivered turn rows, deterministically.

    No model, no database, no language interpretation beyond one structural rule:
    the open goal is the **last delivered user turn that is not an answer to a
    question the assistant asked**. A clarification exchange inserts question and
    answer pairs, so the latest user turn is usually an answer — taking the last
    such turn means a later change of subject also moves the goal instead of
    pinning it to the original request.

    Order comes from `sequence`, never from the caller's list order. Only
    `COMPLETE` delivered rows are turns: `conversations/models.py` guarantees
    content for a `COMPLETE` row and merely permits a string elsewhere, and a
    `PENDING` row is an in-flight placeholder.
    """
    delivered = sorted(
        (
            turn
            for turn in turns
            if _role_value(turn) in _DELIVERED_ROLES
            and _status_value(turn) == "complete"
        ),
        key=lambda turn: int(_field(turn, "sequence")),
    )
    if not delivered:
        return None

    goal: str | None = None
    previous_was_question = False
    for turn in delivered:
        if _role_value(turn) == "assistant":
            previous_was_question = _looks_like_question(_field(turn, "content", ""))
            continue
        if not previous_was_question:
            goal = str(_field(turn, "content", "") or "")
        previous_was_question = False

    if not goal or not goal.strip():
        return None
    return WorkingOpenState(
        open_goal=goal.strip(),
        through_sequence=max(int(_field(turn, "sequence")) for turn in delivered),
    )


def _field(turn: Any, name: str, default: Any = None) -> Any:
    """Read one turn field from either a row object or the worker's message dict.

    The turn path holds `Message` rows and the worker holds dictionaries from
    `_load_messages`. One accessor keeps the derivation rule in one place instead
    of two copies that could drift apart between the synchronous and background
    paths — which is the whole point of both paths sharing a derivation.
    """
    if isinstance(turn, dict):
        return turn.get(name, default)
    return getattr(turn, name, default)


def _role_value(turn: Any) -> str:
    role = _field(turn, "role")
    return str(getattr(role, "value", role) or "").lower()


def _status_value(turn: Any) -> str:
    status = _field(turn, "status")
    if status is None:
        # `Message.__post_init__` coerces an absent status to `COMPLETE`, and the
        # worker's `_is_extractable` documents the same rule. Applying a stricter
        # rule here would make one row complete to the repository and not-complete
        # to this derivation.
        return "complete"
    return str(getattr(status, "value", status) or "").lower()


@dataclass(frozen=True)
class WorkingCandidate:
    """A validated open state that has not yet replaced anything.

    `source_validity` travels with the candidate because it is computed from
    canonical source state by the caller that owns that snapshot, not re-derived
    by the pure replacement policy (`spec:692-702`).
    """

    candidate_id: str
    owner_user_id: str
    conversation_id: str
    origin: WorkingOrigin
    state: WorkingOpenState
    provenance: WorkingProvenance
    retention_mode: RetentionMode
    sensitivity: SensitivityBand
    suppression_generation: int
    source_validity: SourceValidity = SourceValidity.VALID

    def source_cursor(self) -> int:
        """The ordering fact replacement is decided on."""
        return int(self.state.through_sequence)

    def content_identity(self) -> tuple[int, str]:
        """What "the same open state" means, for the identical/no-op comparison."""
        return (self.source_cursor(), str(self.state.open_goal))


def allows_working_formation(record: SourceHandlingRecord | None) -> bool:
    """Whether a persisted record grants *Working* background formation.

    Both halves are required and neither is inferable from the other: the record
    must be the positive authority (`allows_background_formation`) **and** it must
    name the Working family. A semantic or episodic record is positive authority
    for its own family and nothing else, so reusing one here would let one
    family's decision authorize another family's work.
    """
    if not isinstance(record, SourceHandlingRecord):
        return False
    if record.family is not MemoryFamily.WORKING:
        return False
    return allows_background_formation(record)


class WorkingStateTransition:
    """Form one Working Memory candidate, or refuse and return `None`.

    Every refusal returns `None` rather than a partial candidate: a half-derived
    open state is not a lesser open state, it is a different thing the read path
    would treat as usable.
    """

    def __init__(
        self,
        *,
        lifecycle_policy: MemoryLifecyclePolicy | None = None,
        retention_policy: RetentionAssignmentPolicy | None = None,
    ) -> None:
        self._lifecycle_policy = lifecycle_policy or MemoryLifecyclePolicy()
        self._retention_policy = retention_policy or RetentionAssignmentPolicy()

    def derive(
        self,
        *,
        turns: Sequence[Any],
        owner_user_id: str,
        conversation_id: str,
        origin: WorkingOrigin | str,
        source_outbox_id: str,
        source_message_id: str,
        source_handling_record: SourceHandlingRecord | None = None,
        stamped_generation: int = 1,
        current_generation: int = 1,
        source_validity: SourceValidity = SourceValidity.VALID,
        observed_at: datetime | None = None,
        expires_at: datetime | None = None,
        secret_scan_text: str | None = None,
    ) -> WorkingCandidate | None:
        resolved_origin = (
            origin if isinstance(origin, WorkingOrigin) else WorkingOrigin(origin)
        )

        # 1. Positive family-specific authority, for the inferred path only. A
        #    deterministic conversation transition is the explicit-input row of
        #    `spec:1037`, not background formation, so it is not authorized by a
        #    source-handling record and must not require one.
        if resolved_origin is WorkingOrigin.INFERRED_REPLACEMENT and not (
            allows_working_formation(source_handling_record)
        ):
            return None

        # 2. The derivation itself, before anything is paid for.
        state = derive_open_state(turns)
        if validate_working_state(state) is not None:
            return None

        # 3. Pre-model secret scan. The deterministic path runs no model, but the
        #    value is still refused rather than persisted: a prohibited secret
        #    must not become durable instruction state through a family that
        #    happens not to call a provider today.
        if secret_scan_text is not None and (
            detect_prohibited_content(secret_scan_text) is not None
        ):
            return None

        # 4. Retention is the shared policy's decision, not ours. Working state is
        #    conversation-local, so it never outlives its conversation.
        try:
            retention_mode = self._retention_policy.assign(
                scope=MemoryScope.CONVERSATION,
                authority=(
                    Authority.EXPLICIT_STATEMENT
                    if resolved_origin is WorkingOrigin.DETERMINISTIC_TRANSITION
                    else Authority.REPEATED_INFERENCE
                ),
            )
        except ValueError:
            return None

        # 5. Lifecycle eligibility at FORMATION.
        observed = observed_at or datetime.now(timezone.utc)
        decision = self._lifecycle_policy.evaluate(
            stage=LifecycleStage.FORMATION,
            facts=LifecycleFacts(
                retention_mode=retention_mode,
                stamped_generation=stamped_generation,
                current_generation=current_generation,
                scope=MemoryScope.CONVERSATION,
                sensitivity=SensitivityBand.ORDINARY_PERSONAL,
                source_validity=source_validity,
                expires_at=expires_at,
                evaluated_at=observed if expires_at is not None else None,
            ),
        )
        if not decision.eligible:
            return None

        return WorkingCandidate(
            candidate_id=f"wmc_{source_outbox_id}",
            owner_user_id=owner_user_id,
            conversation_id=conversation_id,
            origin=resolved_origin,
            state=state,
            provenance=WorkingProvenance(
                source_outbox_id=source_outbox_id,
                source_message_id=source_message_id,
            ),
            retention_mode=retention_mode,
            sensitivity=SensitivityBand.ORDINARY_PERSONAL,
            suppression_generation=stamped_generation,
            source_validity=source_validity,
        )


class WorkingReplacementReason(str, Enum):
    """Closed reason vocabulary for the replacement decision, in precedence order."""

    CANDIDATE_INVALID = "candidate_invalid"
    LIFECYCLE_DENIED = "lifecycle_denied"
    SOURCE_INVALID = "source_invalid"
    OWNER_MISMATCH = "owner_mismatch"
    CONVERSATION_MISMATCH = "conversation_mismatch"
    STALE_GENERATION = "stale_generation"
    NOT_NEWER = "not_newer"
    CURSOR_CONTENT_CONFLICT = "cursor_content_conflict"
    IDENTICAL_NOOP = "identical_noop"
    REPLACE = "replace"


@dataclass(frozen=True)
class WorkingReplacementDecision:
    replace: bool
    reason: WorkingReplacementReason


class WorkingReplacementPolicy:
    """Decide whether a candidate may replace the canonical open state.

    This is the rule that makes the two formation paths safe to run concurrently,
    so it lives here rather than in call-site ordering. The load-bearing case is
    `NOT_NEWER`: the worker's inferred replacement lags the turn path by
    construction, and without this rule a slow background event would silently
    undo a newer deterministic open state.

    Expiry of the canonical row is deliberately **not** a replacement input.
    Temporal validity is a read-stage concern: an expired row is ineligible, which
    is a reason to replace it, not a reason to keep it.
    """

    def decide(
        self,
        *,
        candidate: WorkingCandidate | None,
        current: "StoredWorkingRow | None" = None,
        source_validity: SourceValidity = SourceValidity.VALID,
        lifecycle_eligible: bool = True,
    ) -> WorkingReplacementDecision:
        def refuse(reason: WorkingReplacementReason) -> WorkingReplacementDecision:
            return WorkingReplacementDecision(replace=False, reason=reason)

        if candidate is None or validate_working_state(candidate.state) is not None:
            return refuse(WorkingReplacementReason.CANDIDATE_INVALID)

        if not lifecycle_eligible:
            return refuse(WorkingReplacementReason.LIFECYCLE_DENIED)

        if (
            candidate.source_validity is SourceValidity.INVALID
            or source_validity is SourceValidity.INVALID
        ):
            return refuse(WorkingReplacementReason.SOURCE_INVALID)

        if current is None:
            return WorkingReplacementDecision(
                replace=True, reason=WorkingReplacementReason.REPLACE
            )

        if candidate.owner_user_id != current.owner_user_id:
            return refuse(WorkingReplacementReason.OWNER_MISMATCH)
        if candidate.conversation_id != current.conversation_id:
            return refuse(WorkingReplacementReason.CONVERSATION_MISMATCH)

        if int(candidate.suppression_generation) != int(current.current_generation):
            return refuse(WorkingReplacementReason.STALE_GENERATION)

        candidate_cursor = candidate.source_cursor()
        current_cursor = int(current.through_sequence)
        if candidate_cursor < current_cursor:
            return refuse(WorkingReplacementReason.NOT_NEWER)
        if candidate_cursor == current_cursor:
            if str(candidate.state.open_goal) == str(current.open_goal):
                return refuse(WorkingReplacementReason.IDENTICAL_NOOP)
            # One cursor is one open state. Two different claims about the same
            # range cannot both stand, and silently keeping the first would make
            # which one wins depend on arrival order.
            return refuse(WorkingReplacementReason.CURSOR_CONTENT_CONFLICT)

        return WorkingReplacementDecision(
            replace=True, reason=WorkingReplacementReason.REPLACE
        )


class WorkingActivationReason(str, Enum):
    """Closed reason vocabulary for Working activation, in precedence order."""

    LIFECYCLE_DENIED = "lifecycle_denied"
    WORKING_GATE_DISABLED = "working_gate_disabled"
    WORKING_GATE_INCONCLUSIVE = "working_gate_inconclusive"
    STALE_GENERATION = "stale_generation"
    SOURCE_INVALID = "source_invalid"
    ELIGIBLE_ACTIVE = "eligible_active"


@dataclass(frozen=True)
class WorkingActivationFacts:
    """Typed, I/O-free snapshot of the facts Working activation needs.

    The two gate flags default to `False` because that is the fail-closed
    direction: a caller that forgets to supply the Working family gate must not
    thereby enable inferred Working activation. The semantic inferred-activation
    flag is deliberately **not** an input — passing semantic evaluation is not
    evidence that Working activation was evaluated.
    """

    origin: WorkingOrigin | str
    lifecycle_eligible: bool
    source_validity: SourceValidity | str
    stamped_generation: int | None
    current_generation: int | None
    working_gate_enabled: bool = False
    working_gate_conclusive: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.source_validity, str):
            object.__setattr__(
                self, "source_validity", SourceValidity(self.source_validity)
            )
        if isinstance(self.origin, str):
            object.__setattr__(self, "origin", WorkingOrigin(self.origin))


@dataclass(frozen=True)
class WorkingActivationDecision:
    target_status: VersionStatus
    reason: WorkingActivationReason
    eligible: bool


class WorkingActivationPolicy:
    """Pure deterministic policy for Working Memory activation.

    Two shapes, not one (`plan v0.22` Activation contract). A deterministic
    governed transition is the explicit-input row and may produce eligible state
    directly. An inferred replacement is the inferred row and stays shadow until
    the Working family gate is a conclusive PASS.

    No semantic threshold and no episodic grounding rule is copied here. The
    semantic 2-turn/3-evidence thresholds answer "how often has the user said
    this", and an episode's grounding answers "did this happen"; Working state's
    question is "what is open right now", which its own source cursor answers.
    """

    def evaluate(self, facts: WorkingActivationFacts) -> WorkingActivationDecision:
        def deny(reason: WorkingActivationReason) -> WorkingActivationDecision:
            return WorkingActivationDecision(
                target_status=VersionStatus.SHADOW, reason=reason, eligible=False
            )

        # 1. The shared lifecycle owner still decides eligibility.
        if not facts.lifecycle_eligible:
            return deny(WorkingActivationReason.LIFECYCLE_DENIED)

        # 2. The Working family/type rollout gate, default off, and only for the
        #    inferred shape.
        if facts.origin is WorkingOrigin.INFERRED_REPLACEMENT:
            if not facts.working_gate_enabled:
                return deny(WorkingActivationReason.WORKING_GATE_DISABLED)
            if not facts.working_gate_conclusive:
                return deny(WorkingActivationReason.WORKING_GATE_INCONCLUSIVE)

        # 3. Current canonical state, not a default.
        if (
            facts.stamped_generation is None
            or facts.current_generation is None
            or int(facts.stamped_generation) != int(facts.current_generation)
        ):
            return deny(WorkingActivationReason.STALE_GENERATION)
        if facts.source_validity is SourceValidity.INVALID:
            return deny(WorkingActivationReason.SOURCE_INVALID)

        return WorkingActivationDecision(
            target_status=VersionStatus.ACTIVE,
            reason=WorkingActivationReason.ELIGIBLE_ACTIVE,
            eligible=True,
        )


class WorkingAbstentionReason(str, Enum):
    """Closed vocabulary for why Working selection returned nothing."""

    NO_ELIGIBLE_WORKING_STATE = "no_eligible_working_state"


@dataclass(frozen=True)
class WorkingReadRequest:
    """An exact typed Working Memory query.

    Working state is one open state per conversation, so the request is a
    conversation identity and nothing else. There is no free-text or fuzzy field:
    matching on a string would be the retrieval-projection work the plan defers to
    Task 14.
    """

    owner_user_id: str
    conversation_id: str

    def __post_init__(self) -> None:
        for field_name in ("owner_user_id", "conversation_id"):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{field_name} must be a non-empty string.")


@dataclass(frozen=True)
class StoredWorkingRow:
    """One physical Working Memory row, coerced back to domain vocabulary.

    Storage-scoped only. This row does not say whether the state is
    answer-eligible — `MemoryLifecyclePolicy` decides that, in the read engine.
    """

    summary_id: str
    owner_user_id: str
    conversation_id: str
    open_goal: str
    through_sequence: int
    retention_mode: RetentionMode
    stamped_generation: int
    current_generation: int
    status: VersionStatus
    sensitivity: SensitivityBand
    source_validity: SourceValidity
    expires_at: datetime | None = None


@dataclass(frozen=True)
class SelectedWorkingState:
    """The governed projection handed to dialogue-state reconstruction.

    Structured fields only. The source identity, the source-handling row, the
    deleted-source provenance and the legacy `content` column stay behind: an open
    state that carried its raw source would be a prompt-instruction channel
    (`spec:1079`).
    """

    open_goal: str
    through_sequence: int
    conversation_id: str


@dataclass(frozen=True)
class WorkingSelection:
    selected: tuple[SelectedWorkingState, ...]
    abstention_reason: WorkingAbstentionReason | None = None


class WorkingStore(Protocol):
    def get_storage_scoped(
        self, request: WorkingReadRequest
    ) -> Sequence[StoredWorkingRow]: ...


class WorkingMemoryReadEngine:
    """Eligibility and abstention for one conversation's Working Memory.

    Abstention is a real outcome, not an error: a conversation with no eligible
    open state gets `NO_ELIGIBLE_WORKING_STATE` and dialogue reconstruction
    proceeds from recent turns alone.
    """

    def __init__(
        self,
        store: WorkingStore,
        lifecycle: MemoryLifecyclePolicy | None = None,
        clock: Any | None = None,
    ) -> None:
        self._store = store
        self._lifecycle = lifecycle or MemoryLifecyclePolicy()
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def select(self, request: WorkingReadRequest) -> WorkingSelection:
        rows = tuple(self._store.get_storage_scoped(request))
        evaluated_at = self._clock()

        for row in rows:
            if row.owner_user_id != request.owner_user_id:
                continue
            if row.conversation_id != request.conversation_id:
                continue
            decision = self._lifecycle.evaluate(
                stage=LifecycleStage.READ,
                facts=LifecycleFacts(
                    retention_mode=row.retention_mode,
                    stamped_generation=row.stamped_generation,
                    current_generation=row.current_generation,
                    scope=MemoryScope.CONVERSATION,
                    sensitivity=row.sensitivity,
                    source_validity=row.source_validity,
                    status=row.status,
                    expires_at=row.expires_at,
                    evaluated_at=evaluated_at if row.expires_at is not None else None,
                ),
            )
            if decision.eligible:
                return WorkingSelection(
                    selected=(
                        SelectedWorkingState(
                            open_goal=str(row.open_goal),
                            through_sequence=int(row.through_sequence),
                            conversation_id=str(row.conversation_id),
                        ),
                    )
                )

        return WorkingSelection(
            selected=(),
            abstention_reason=WorkingAbstentionReason.NO_ELIGIBLE_WORKING_STATE,
        )
