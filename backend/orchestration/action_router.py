"""Deterministic routing, and the authorization boundary that guards mutation.

Two responsibilities, one file, because the second is what the first consults:

- `ActionRouter` is pure application logic. It chooses
  `NORMAL_QUERY | EXPLICIT_MEMORY_ACTION | NEEDS_CLARIFICATION` (`spec:367-373`)
  and executes nothing.
- `ExplicitIntentGate` decides whether a durable remember/correct/forget is
  permitted at all. It is an authorization boundary, not a second extractor
  (`ADR 0036:34-41`).

The gate's rule is deliberately narrow: a durable mode is authorized only when
the reading carries `UnderstandingReason.DETERMINISTIC_MATCH`, a reason the closed
deterministic rules in `turn_understanding` are the only producer of. A model may
parse a payload after that gate, but its output arrives with some other reason
code, so classification alone cannot acquire authority — and a future parser
cannot accidentally gain it by inventing a reason code, because every code except
the deterministic one is denied.

Nothing here writes, reads storage, or calls a provider.
"""

from __future__ import annotations

from backend.orchestration.turn_models import (
    DURABLE_ACTION_MODES,
    ExplicitIntentDecision,
    InteractionMode,
    RoutingDecision,
    TurnUnderstandingResult,
    UnderstandingReason,
)


class ExplicitIntentGate:
    """Authorize a durable explicit Memory action, deterministically.

    Read-only modes such as `explicit_inspect` do not pass through this gate:
    they propose no mutation (`spec:397-401`).
    """

    def authorize(self, result: TurnUnderstandingResult) -> ExplicitIntentDecision:
        """Return whether `result` may proceed to a durable mutation.

        A denial always names a cause. `PARSER_FAILED_CLOSED` and the other
        non-deterministic codes are the vocabulary's way of saying "something
        interpreted this, but not the corroborated rule", so they are reported
        rather than collapsed into a generic refusal.
        """
        if result.interaction_mode not in DURABLE_ACTION_MODES:
            return ExplicitIntentDecision(
                authorized=False,
                reason_code=UnderstandingReason.NO_EXPLICIT_SIGNAL,
            )

        if (
            UnderstandingReason.DETERMINISTIC_MATCH not in result.reason_codes
            or result.needs_clarification
        ):
            # Report the reading's own cause when it has one. Falling back to
            # "no explicit signal" for a reading that plainly had one would
            # misdescribe why the gate refused.
            fallback = (
                UnderstandingReason.AMBIGUOUS_SPEECH_ACT
                if result.needs_clarification
                else UnderstandingReason.NO_EXPLICIT_SIGNAL
            )
            denial = next(
                (
                    reason
                    for reason in result.reason_codes
                    if reason is not UnderstandingReason.DETERMINISTIC_MATCH
                ),
                fallback,
            )
            return ExplicitIntentDecision(authorized=False, reason_code=denial)

        return ExplicitIntentDecision(
            authorized=True,
            reason_code=UnderstandingReason.DETERMINISTIC_MATCH,
        )


class ActionRouter:
    """Choose the branch for one bounded turn."""

    def __init__(self, gate: ExplicitIntentGate | None = None) -> None:
        self._gate = gate if gate is not None else ExplicitIntentGate()

    def route(self, result: TurnUnderstandingResult) -> RoutingDecision:
        """Return the branch `result` takes.

        A durable mode reaches `EXPLICIT_MEMORY_ACTION` only after the gate
        corroborates it; otherwise the turn asks for clarification instead of
        acting on an uncorroborated speech act. `explicit_inspect` routes to the
        Memory branch without the gate, because it proposes no mutation, and the
        orchestrator reports its capability as unavailable until Stage 3.
        """
        if result.interaction_mode is InteractionMode.EXPLICIT_INSPECT:
            return RoutingDecision.EXPLICIT_MEMORY_ACTION

        if result.interaction_mode in DURABLE_ACTION_MODES:
            decision = self._gate.authorize(result)
            return (
                RoutingDecision.EXPLICIT_MEMORY_ACTION
                if decision.authorized
                else RoutingDecision.NEEDS_CLARIFICATION
            )

        if result.interaction_mode is InteractionMode.AMBIGUOUS:
            return RoutingDecision.NEEDS_CLARIFICATION

        return RoutingDecision.NORMAL_QUERY
