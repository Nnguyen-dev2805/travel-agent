"""Risk-based write policy: eligibility, sensitivity, and decisions.

Confirm-all is superseded. An ordinary preference from an explicit
command is direct-write-eligible with no second confirmation; valid
background evidence stays shadow; restricted or contextually sensitive
content is held with no durable write; prohibited content is rejected
before any candidate effect. Hard-policy failures are never shadow.

Decisions return data only: this module never touches durable state,
never renders UI state, and never creates confirmation tokens. It
depends on the Python standard library and the sibling contract,
registry, and secret modules only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.memory.write_pipeline.models import (
    SENSITIVITY_RANK,
    Authority,
    DecisionOutcome,
    DecisionReason,
    MemoryCandidate,
    MemoryDecisionDraft,
    SensitivityBand,
)
from backend.memory.write_pipeline.registry import (
    RegistryValidationError,
    UnknownKeyError,
    UnknownValueError,
    is_known_key,
    validate_against_registry,
)


class Actor(str, Enum):
    """Who produced the evidence behind one candidate."""

    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"
    EXTERNAL = "external"
    SYSTEM = "system"


class Origin(str, Enum):
    """How one candidate reached policy: explicit command or background."""

    EXPLICIT_COMMAND = "explicit_command"
    BACKGROUND_CHAT = "background_chat"


class EligibilityOutcome(str, Enum):
    """Closed eligibility verdicts for one candidate."""

    ELIGIBLE = "eligible"
    INELIGIBLE_AUTH = "ineligible_auth"
    INELIGIBLE_ACTOR = "ineligible_actor"
    INELIGIBLE_SOURCE = "ineligible_source"
    INELIGIBLE_KEY = "ineligible_key"


@dataclass(frozen=True)
class DecisionContext:
    """The evaluated setting around one candidate decision.

    Security fields carry no defaults: every caller must state the
    actor, the authentication result, the origin, and the source
    lifecycle explicitly, so a missing field fails closed instead of
    silently passing as an authenticated user command.
    """

    actor: Actor | str
    authenticated: bool
    origin: Origin | str
    source_deleted: bool
    contextual_sensitivity: SensitivityBand | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "actor", _coerce_actor(self.actor))
        if self.authenticated is not True and self.authenticated is not False:
            raise ValueError("Field 'authenticated' must be a boolean.")
        object.__setattr__(self, "origin", _coerce_origin(self.origin))
        if self.source_deleted is not True and self.source_deleted is not False:
            raise ValueError("Field 'source_deleted' must be a boolean.")
        if self.contextual_sensitivity is not None:
            object.__setattr__(
                self,
                "contextual_sensitivity",
                _coerce_sensitivity(self.contextual_sensitivity),
            )


def _coerce_actor(value: Any) -> Actor:
    if isinstance(value, Actor):
        return value
    if isinstance(value, str):
        try:
            return Actor(value)
        except ValueError as error:
            raise ValueError("Unknown actor value.") from error
    raise ValueError("Field 'actor' must be an Actor value.")


def _coerce_origin(value: Any) -> Origin:
    if isinstance(value, Origin):
        return value
    if isinstance(value, str):
        try:
            return Origin(value)
        except ValueError as error:
            raise ValueError("Unknown origin value.") from error
    raise ValueError("Field 'origin' must be an Origin value.")


def _coerce_sensitivity(value: Any) -> SensitivityBand:
    if isinstance(value, SensitivityBand):
        return value
    if isinstance(value, str):
        try:
            return SensitivityBand(value)
        except ValueError as error:
            raise ValueError("Unknown sensitivity value.") from error
    raise ValueError("Field 'sensitivity' must be a SensitivityBand value.")


def evaluate_eligibility(
    *,
    actor: Actor | str,
    authenticated: bool,
    source_deleted: bool,
    canonical_key: Any,
) -> EligibilityOutcome:
    """Decide whether one candidate may be considered for a write at all.

    Checks run in authentication, source-lifecycle, key, then actor
    order; each verdict is deterministic and carries no content.
    """
    if authenticated is not True:
        return EligibilityOutcome.INELIGIBLE_AUTH
    if source_deleted is True:
        return EligibilityOutcome.INELIGIBLE_SOURCE
    if not is_known_key(canonical_key):
        return EligibilityOutcome.INELIGIBLE_KEY
    if _coerce_actor(actor) is not Actor.USER:
        return EligibilityOutcome.INELIGIBLE_ACTOR
    return EligibilityOutcome.ELIGIBLE


def classify_sensitivity(
    *,
    floor: SensitivityBand | str,
    secret_hit: bool,
    contextual: SensitivityBand | str | None = None,
) -> SensitivityBand:
    """Combine the registry floor with detection and contextual signals.

    A secret hit always lands on prohibited. Otherwise the result is the
    highest of the floor and the contextual signal, so contextual
    judgment may only raise sensitivity, never lower it.
    """
    if secret_hit is True:
        return SensitivityBand.PROHIBITED_SECRET
    resolved_floor = _coerce_sensitivity(floor)
    if contextual is None:
        return resolved_floor
    resolved_context = _coerce_sensitivity(contextual)
    if SENSITIVITY_RANK[resolved_context] > SENSITIVITY_RANK[resolved_floor]:
        return resolved_context
    return resolved_floor


def _invalid_reason(error: RegistryValidationError) -> DecisionReason:
    if isinstance(error, UnknownKeyError):
        return DecisionReason.INVALID_KEY
    if isinstance(error, UnknownValueError):
        return DecisionReason.INVALID_VALUE
    return {
        "scope_not_allowed": DecisionReason.INVALID_SCOPE,
        "sensitivity_below_floor": DecisionReason.INVALID_SENSITIVITY,
        "condition_not_supported": DecisionReason.INVALID_CONDITION,
    }.get(error.reason, DecisionReason.INVALID_KEY)


def _decide(
    candidate: MemoryCandidate, context: DecisionContext
) -> tuple[DecisionOutcome, DecisionReason]:
    try:
        validate_against_registry(candidate)
    except RegistryValidationError as error:
        return DecisionOutcome.INVALID, _invalid_reason(error)
    eligibility = evaluate_eligibility(
        actor=context.actor,
        authenticated=context.authenticated,
        source_deleted=context.source_deleted,
        canonical_key=candidate.canonical_key,
    )
    if eligibility is EligibilityOutcome.INELIGIBLE_KEY:
        return DecisionOutcome.INVALID, DecisionReason.INVALID_KEY
    if eligibility is EligibilityOutcome.INELIGIBLE_AUTH:
        return DecisionOutcome.REJECTED, DecisionReason.REJECTED_AUTH
    if eligibility is EligibilityOutcome.INELIGIBLE_ACTOR:
        return DecisionOutcome.REJECTED, DecisionReason.REJECTED_ACTOR
    if eligibility is EligibilityOutcome.INELIGIBLE_SOURCE:
        return DecisionOutcome.REJECTED, DecisionReason.REJECTED_SOURCE
    if candidate.sensitivity is SensitivityBand.PROHIBITED_SECRET:
        return DecisionOutcome.REJECTED, DecisionReason.REJECTED_PROHIBITED
    effective = classify_sensitivity(
        floor=candidate.sensitivity,
        secret_hit=False,
        contextual=context.contextual_sensitivity,
    )
    if effective is SensitivityBand.PROHIBITED_SECRET:
        return DecisionOutcome.REJECTED, DecisionReason.REJECTED_PROHIBITED
    if effective in (
        SensitivityBand.CONTEXTUALLY_SENSITIVE,
        SensitivityBand.RESTRICTED,
    ):
        return DecisionOutcome.HELD_SENSITIVE, DecisionReason.HELD_SENSITIVE
    if (
        context.origin is Origin.EXPLICIT_COMMAND
        and candidate.authority is Authority.EXPLICIT_SAVE
    ):
        return DecisionOutcome.DIRECT_WRITE, DecisionReason.DIRECT_WRITE_ELIGIBLE
    return DecisionOutcome.SHADOW, DecisionReason.SHADOW_VALID_UNPROMOTED


def decide_candidate(
    candidate: MemoryCandidate, context: DecisionContext
) -> MemoryDecisionDraft:
    """Decide one candidate's write permission and return the draft decision.

    Data only: the returned draft names an outcome and a governed
    reason. It performs no durable write, mints no identifier, reads
    no clock, and carries no candidate text, so prohibited values
    cannot leak through it and repeated calls stay fully equal.
    """
    if not isinstance(candidate, MemoryCandidate):
        raise ValueError("decide_candidate requires a MemoryCandidate.")
    if not isinstance(context, DecisionContext):
        raise ValueError("decide_candidate requires a DecisionContext.")
    outcome, reason = _decide(candidate, context)
    return MemoryDecisionDraft(
        candidate_id=candidate.candidate_id,
        outcome=outcome,
        reason=reason,
    )
