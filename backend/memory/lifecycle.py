"""The single owner of shared Memory lifecycle rules.

`MemoryLifecyclePolicy` answers one question — *is this Memory eligible at this
stage?* — for the four paths that must all agree: write, formation, activation,
and read (`ADR 0037`). `RetentionAssignmentPolicy` sits beside it answering a
different one — *what retention does this new version get?* — because assignment
happens **before** a version exists, while evaluation reads a decision that was
already persisted. Merging them would let a later policy version silently
re-interpret historical Memory.

Three properties this module exists to guarantee:

- **Fail closed.** A fact a stage requires but did not receive denies with
  `MISSING_REQUIRED_FACT`. Absence is never treated as satisfied, and `None` is
  never read as "not applicable" — a caller that means `NOT_REQUIRED` says so.
- **Deterministic reason.** When several predicates fail, the reported reason is
  the first in `_REASON_PRECEDENCE`, so identical facts always produce an
  identical explanation.
- **No caller awareness.** Execution mode is not an input. The API path and the
  worker path consume the same policy, which is what stops the two from drifting
  into different eligibility rules.

Pure domain policy: no database, no model, no provider, no clock. Temporal
validity is evaluated against a time the caller supplies, never against
`datetime.now()`, so the decision is reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from backend.memory.write_pipeline.models import (
    SENSITIVITY_RANK,
    Authority,
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    SourceValidity,
    VersionStatus,
)


class LifecycleStage(str, Enum):
    """Where in the pipeline eligibility is being asked about.

    `WRITE`, `FORMATION`, and `ACTIVATION` apply only the lifecycle predicates
    that exist before an active version does. `READ` is the full predicate and
    the only stage with a lifecycle status to check.
    """

    WRITE = "write"
    FORMATION = "formation"
    ACTIVATION = "activation"
    READ = "read"


class LifecycleReason(str, Enum):
    """Closed reason vocabulary, in precedence order.

    Free text may explain a decision in a log line; it never decides one. The
    order of these members is normative — see `_REASON_PRECEDENCE`.
    """

    MISSING_REQUIRED_FACT = "missing_required_fact"
    SCOPE_INELIGIBLE = "scope_ineligible"
    SENSITIVITY_INELIGIBLE = "sensitivity_ineligible"
    STALE_GENERATION = "stale_generation"
    EXPIRED = "expired"
    SOURCE_INVALID = "source_invalid"
    STATUS_INELIGIBLE = "status_ineligible"
    ELIGIBLE = "eligible"


#: The precedence the policy reports in. Written once, and asserted by test.
_REASON_PRECEDENCE = (
    LifecycleReason.MISSING_REQUIRED_FACT,
    LifecycleReason.SCOPE_INELIGIBLE,
    LifecycleReason.SENSITIVITY_INELIGIBLE,
    LifecycleReason.STALE_GENERATION,
    LifecycleReason.EXPIRED,
    LifecycleReason.SOURCE_INVALID,
    LifecycleReason.STATUS_INELIGIBLE,
)

#: Retention modes whose value depends on its source staying valid.
_SOURCE_DEPENDENT_RETENTION = frozenset(
    {RetentionMode.CONVERSATION_BOUND, RetentionMode.SOURCE_BOUND}
)


def _coerce(value: Any, field: str, enum_type: type[Enum]) -> Any:
    if value is None:
        return None
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError as error:
            allowed = ", ".join(member.value for member in enum_type)
            raise ValueError(
                f"Unknown {field} value. Allowed values: {allowed}."
            ) from error
    raise ValueError(f"Field '{field}' must be a {enum_type.__name__} value or null.")


@dataclass(frozen=True)
class LifecycleFacts:
    """A typed, I/O-free snapshot of the lifecycle inputs one stage needs.

    Every field is optional at the type level and `None` means *the caller did
    not supply this fact* — which the policy treats as a denial when the stage
    requires it. That is the whole fail-closed mechanism: there is no sentinel
    that means "assume fine".
    """

    retention_mode: RetentionMode | str | None = None
    stamped_generation: int | None = None
    current_generation: int | None = None
    scope: MemoryScope | str | None = None
    sensitivity: SensitivityBand | str | None = None
    source_validity: SourceValidity | str | None = None
    status: VersionStatus | str | None = None
    expires_at: datetime | None = None
    evaluated_at: datetime | None = None
    #: The registry entry's allowed scopes and sensitivity floor, when the
    #: caller wants the policy to re-check them. `None` means the caller did not
    #: supply a constraint, not that the constraint is empty.
    allowed_scopes: tuple[MemoryScope, ...] | None = None
    minimum_sensitivity: SensitivityBand | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "retention_mode",
            _coerce(self.retention_mode, "retention_mode", RetentionMode),
        )
        object.__setattr__(
            self, "scope", _coerce(self.scope, "scope", MemoryScope)
        )
        object.__setattr__(
            self,
            "sensitivity",
            _coerce(self.sensitivity, "sensitivity", SensitivityBand),
        )
        object.__setattr__(
            self,
            "source_validity",
            _coerce(self.source_validity, "source_validity", SourceValidity),
        )
        object.__setattr__(
            self, "status", _coerce(self.status, "status", VersionStatus)
        )
        object.__setattr__(
            self,
            "minimum_sensitivity",
            _coerce(
                self.minimum_sensitivity, "minimum_sensitivity", SensitivityBand
            ),
        )
        if self.allowed_scopes is not None:
            object.__setattr__(
                self,
                "allowed_scopes",
                tuple(
                    _coerce(scope, "allowed_scopes entry", MemoryScope)
                    for scope in self.allowed_scopes
                ),
            )
        for field_name in ("stamped_generation", "current_generation"):
            value = getattr(self, field_name)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"Field '{field_name}' must be an integer or null.")
            # A generation is a forget era counter that starts at 1; zero or a
            # negative value is not a fact any writer could have stored, so it
            # is refused instead of being allowed to pass an equality check.
            if value < 1:
                raise ValueError(
                    f"Field '{field_name}' must be a positive generation "
                    "(>= 1)."
                )


@dataclass(frozen=True)
class LifecycleDecision:
    """Whether the facts satisfy the stage, and the one reason why."""

    eligible: bool
    reason: LifecycleReason


def _decision(reason: LifecycleReason) -> LifecycleDecision:
    return LifecycleDecision(
        eligible=reason is LifecycleReason.ELIGIBLE, reason=reason
    )


class MemoryLifecyclePolicy:
    """Decide eligibility for one stage from one typed fact snapshot."""

    def evaluate(
        self,
        *,
        stage: LifecycleStage,
        facts: LifecycleFacts,
    ) -> LifecycleDecision:
        """Return the first applicable reason, in the normative order."""
        if not isinstance(stage, LifecycleStage):
            raise ValueError("Field 'stage' must be a LifecycleStage value.")
        if not isinstance(facts, LifecycleFacts):
            raise ValueError("Field 'facts' must be a LifecycleFacts value.")

        for predicate in _PREDICATES:
            reason = predicate(stage, facts)
            if reason is not None:
                return _decision(reason)
        return _decision(LifecycleReason.ELIGIBLE)


# --- Predicates, in precedence order ---------------------------------------


def _missing_required_fact(
    stage: LifecycleStage, facts: LifecycleFacts
) -> LifecycleReason | None:
    """Every stage needs the same five facts, plus its own extras.

    `source_validity` is required at every stage and retention mode. For a
    source-dependent mode a *present but inapplicable* `NOT_REQUIRED` is also
    missing: the caller has told us the fact does not apply to a version whose
    eligibility depends on it, which is a contradiction rather than a pass.
    """
    for field_name in (
        "retention_mode",
        "stamped_generation",
        "current_generation",
        "scope",
        "sensitivity",
        "source_validity",
    ):
        if getattr(facts, field_name) is None:
            return LifecycleReason.MISSING_REQUIRED_FACT
    if (
        facts.retention_mode in _SOURCE_DEPENDENT_RETENTION
        and facts.source_validity is SourceValidity.NOT_REQUIRED
    ):
        return LifecycleReason.MISSING_REQUIRED_FACT
    if stage is LifecycleStage.READ and facts.status is None:
        return LifecycleReason.MISSING_REQUIRED_FACT
    if facts.expires_at is not None and facts.evaluated_at is None:
        return LifecycleReason.MISSING_REQUIRED_FACT
    return None


def _scope_ineligible(
    stage: LifecycleStage, facts: LifecycleFacts
) -> LifecycleReason | None:
    """Only checked when the caller supplied the entry's allowed scopes."""
    if facts.allowed_scopes is not None and facts.scope not in facts.allowed_scopes:
        return LifecycleReason.SCOPE_INELIGIBLE
    return None


def _sensitivity_ineligible(
    stage: LifecycleStage, facts: LifecycleFacts
) -> LifecycleReason | None:
    """A prohibited secret is denied everywhere; a floor is denied when supplied."""
    if facts.sensitivity is SensitivityBand.PROHIBITED_SECRET:
        return LifecycleReason.SENSITIVITY_INELIGIBLE
    if (
        facts.minimum_sensitivity is not None
        and SENSITIVITY_RANK[facts.sensitivity]
        < SENSITIVITY_RANK[facts.minimum_sensitivity]
    ):
        return LifecycleReason.SENSITIVITY_INELIGIBLE
    return None


def _stale_generation(
    stage: LifecycleStage, facts: LifecycleFacts
) -> LifecycleReason | None:
    """A generation-N artifact cannot form, activate, or read after N+1."""
    if facts.stamped_generation != facts.current_generation:
        return LifecycleReason.STALE_GENERATION
    return None


def _expired(stage: LifecycleStage, facts: LifecycleFacts) -> LifecycleReason | None:
    """Temporal validity only. Never used to encode source or forget state."""
    if facts.expires_at is not None and facts.evaluated_at >= facts.expires_at:
        return LifecycleReason.EXPIRED
    return None


def _source_invalid(
    stage: LifecycleStage, facts: LifecycleFacts
) -> LifecycleReason | None:
    if facts.source_validity is SourceValidity.INVALID:
        return LifecycleReason.SOURCE_INVALID
    return None


def _status_ineligible(
    stage: LifecycleStage, facts: LifecycleFacts
) -> LifecycleReason | None:
    """`READ` requires an `ACTIVE` version; earlier stages have no status."""
    if stage is LifecycleStage.READ and facts.status is not VersionStatus.ACTIVE:
        return LifecycleReason.STATUS_INELIGIBLE
    return None


#: Evaluated in this order; the first to return a reason wins.
_PREDICATES = (
    _missing_required_fact,
    _scope_ineligible,
    _sensitivity_ineligible,
    _stale_generation,
    _expired,
    _source_invalid,
    _status_ineligible,
)


#: The closed retention assignment table, written once.
#:
#: A table rather than a chain of `if`s, because a chain has to end in
#: *something*: the first version ended in `return SOURCE_BOUND`, so a caller
#: that passed no scope — or a vocabulary that grew a member — received a
#: retention decision for a combination nobody had reviewed. Assignment is a
#: privacy decision and has no default.
_RETENTION_BY_SCOPE_AND_AUTHORITY: dict[
    tuple[MemoryScope, Authority], RetentionMode
] = {
    (MemoryScope.CONVERSATION, Authority.EXPLICIT_SAVE): (
        RetentionMode.CONVERSATION_BOUND
    ),
    (MemoryScope.CONVERSATION, Authority.EXPLICIT_STATEMENT): (
        RetentionMode.CONVERSATION_BOUND
    ),
    (MemoryScope.CONVERSATION, Authority.REPEATED_INFERENCE): (
        RetentionMode.CONVERSATION_BOUND
    ),
    (MemoryScope.USER, Authority.EXPLICIT_SAVE): RetentionMode.USER_DURABLE,
    (MemoryScope.USER, Authority.EXPLICIT_STATEMENT): RetentionMode.SOURCE_BOUND,
    (MemoryScope.USER, Authority.REPEATED_INFERENCE): RetentionMode.SOURCE_BOUND,
}


class RetentionAssignmentPolicy:
    """Assign one retention mode to a version about to be written.

    Separate from `MemoryLifecyclePolicy` on purpose. Assignment consumes the
    facts known *before* a version exists (scope and authority) and produces the
    decision that is then persisted with that version; evaluation consumes the
    persisted decision and never re-derives it. That split is what stops a later
    policy revision from silently re-interpreting historical Memory.
    """

    def assign(
        self,
        *,
        scope: MemoryScope | str,
        authority: Authority | str,
    ) -> RetentionMode:
        """Return the governed retention mode, or refuse the combination.

        The mapping is closed and deliberately conservative: conversation-local
        state never outlives its conversation, and `USER_DURABLE` is earned only
        by a corroborated save. A plain statement is evidence, not durable-save
        intent, and inferred state stays tied to its provenance (`spec v0.7`).

        An absent or ungoverned input raises. There is no fallback: every
        combination the vocabularies can currently produce is in the table, so
        an unlisted pair can only mean a vocabulary grew without the table
        growing with it — the one case that must not be guessed.
        """
        if scope is None or authority is None:
            raise ValueError(
                "Retention assignment requires both a scope and an authority; "
                "an absent input is not a governed combination."
            )
        resolved_scope = _coerce(scope, "scope", MemoryScope)
        resolved_authority = _coerce(authority, "authority", Authority)
        try:
            return _RETENTION_BY_SCOPE_AND_AUTHORITY[
                (resolved_scope, resolved_authority)
            ]
        except KeyError as error:
            raise ValueError(
                f"No retention is governed for scope '{resolved_scope.value}' "
                f"with authority '{resolved_authority.value}'. Extend the "
                "closed mapping explicitly rather than defaulting."
            ) from error
