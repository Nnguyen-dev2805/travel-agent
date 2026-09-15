"""Task 3: `TurnDisposition` is a reasoning outcome, not a storage status.

`MessageStatus` (ADR 0023) describes persistence completeness. `TurnDisposition`
describes what the bounded agentic turn achieved. They are orthogonal dimensions
with constrained valid combinations (`spec:332-363`), and the disposition stays
internal to `TurnOutcome` in the first rollout — it is never a public Chat field
(`spec:360-363`).

The combination table is pinned as a **total** classification: every
`(MessageStatus, TurnDisposition | None)` pair is either accepted or rejected, so
a fifth disposition cannot be added without a test noticing. That mirrors the
existing idiom for exactly this hazard in `test_fence_reason.py`.

No test here touches a database, a model, HTTP, or the network.
"""

from __future__ import annotations

import ast
import dataclasses
from pathlib import Path

import pytest

from backend.app.schemas.chat import ChatResponse
from backend.conversations.models import MessageStatus
from backend.orchestration.turn_models import (
    ContextMode,
    ContextPlan,
    ExplicitIntentDecision,
    InteractionMode,
    RoutingDecision,
    TurnDisposition,
    TurnUnderstandingResult,
    UnderstandingReason,
    disposition_is_valid,
)

ANSWERED = TurnDisposition.ANSWERED
NEEDS_CLARIFICATION = TurnDisposition.NEEDS_CLARIFICATION
INCOMPLETE = TurnDisposition.INCOMPLETE
EXECUTION_FAILED = TurnDisposition.EXECUTION_FAILED

#: The approved matrix (`plan:352-356`, `spec:352-356`), written out once.
#: `None` means "not finalized yet", which is the only value `PENDING` admits.
VALID_COMBINATIONS: dict[MessageStatus, frozenset[TurnDisposition | None]] = {
    MessageStatus.PENDING: frozenset({None}),
    MessageStatus.FAILED: frozenset({NEEDS_CLARIFICATION, INCOMPLETE, EXECUTION_FAILED}),
    MessageStatus.COMPLETE: frozenset(
        {ANSWERED, NEEDS_CLARIFICATION, INCOMPLETE, EXECUTION_FAILED}
    ),
}

ALL_DISPOSITIONS: tuple[TurnDisposition | None, ...] = (
    ANSWERED,
    NEEDS_CLARIFICATION,
    INCOMPLETE,
    EXECUTION_FAILED,
    None,
)

ALL_PAIRS = [
    (status, disposition)
    for status in MessageStatus
    for disposition in ALL_DISPOSITIONS
]


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an `import`/`from ... import` in one source file."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_the_four_dispositions_are_exactly_the_specified_vocabulary():
    """A fifth value would be a new reasoning outcome nobody approved."""
    assert {member.value for member in TurnDisposition} == {
        "answered",
        "needs_clarification",
        "incomplete",
        "execution_failed",
    }


def test_the_vocabulary_is_total():
    """Every member must appear somewhere in the matrix.

    An unclassified member would default to whichever branch a caller happened
    to write — which is how the six-way fence reason collapsed into one sentence
    before ADR 0033.
    """
    classified: set[TurnDisposition] = set()
    for dispositions in VALID_COMBINATIONS.values():
        classified.update(d for d in dispositions if d is not None)
    assert classified == set(TurnDisposition)


def test_every_status_is_classified():
    """A new `MessageStatus` must not slip past the matrix silently."""
    assert set(VALID_COMBINATIONS) == set(MessageStatus)


@pytest.mark.parametrize("status,disposition", ALL_PAIRS)
def test_the_combination_matrix_is_total(status, disposition):
    expected = disposition in VALID_COMBINATIONS[status]
    assert disposition_is_valid(status, disposition) is expected


def test_pending_has_no_finalized_disposition():
    """`PENDING` is in flight, so nothing is finalized yet (`spec:352-354`)."""
    for disposition in TurnDisposition:
        assert disposition_is_valid(MessageStatus.PENDING, disposition) is False
    assert disposition_is_valid(MessageStatus.PENDING, None) is True


def test_a_failed_row_can_never_be_answered():
    """A persisted failure cannot have produced an answer (`spec:353-354`)."""
    assert disposition_is_valid(MessageStatus.FAILED, ANSWERED) is False


def test_a_complete_row_accepts_all_four():
    """`EXECUTION_FAILED` on a complete row reports a limitation, not a
    persistence failure — the reply itself was stored (`spec:355-358`)."""
    for disposition in TurnDisposition:
        assert disposition_is_valid(MessageStatus.COMPLETE, disposition) is True


def test_a_terminal_row_requires_a_disposition():
    """A terminal status with nothing finalized is not a valid combination."""
    for status in (MessageStatus.FAILED, MessageStatus.COMPLETE):
        assert disposition_is_valid(status, None) is False


def test_the_disposition_serialises_as_a_plain_string():
    """A `str` enum, so it logs and compares without a conversion step."""
    assert isinstance(ANSWERED, str)
    assert ANSWERED == "answered"


def test_the_public_chat_response_exposes_no_disposition():
    """The plan's review gate: `TurnDisposition` stays internal (`plan:367-368`).

    Only the absence is asserted. Pinning the whole field set would break this
    Task 3 test the moment an unrelated Chat field is added.
    """
    assert "disposition" not in ChatResponse.model_fields


def test_turn_models_reaches_no_storage_model_or_web_framework():
    """Domain modules import no FastAPI/SQLAlchemy/provider/RAG (`spec:555-556`).

    `backend.conversations` is deliberately absent from this list: orchestration
    depends on conversations (`orchestration/__init__.py:8-9`), and the matrix is
    defined over `MessageStatus`.
    """
    forbidden = (
        "fastapi",
        "sqlalchemy",
        "backend.memory",
        "backend.rag",
        "backend.observability",
        "backend.storage",
    )
    path = Path(__file__).resolve().parents[3] / "orchestration" / "turn_models.py"
    imported = _imported_modules(path)

    assert not [
        module
        for module in imported
        for banned in forbidden
        if module == banned or module.startswith(f"{banned}.")
    ], imported


# ---------------------------------------------------------------------------
# Task 4 contracts — the closed vocabularies and result types the Stage-1
# understanding / routing / planning flow is built from.
# ---------------------------------------------------------------------------


def test_interaction_mode_is_the_closed_spec_vocabulary():
    """`spec:306-308` fixes the six values; a seventh is a new approved mode."""
    assert {member.value for member in InteractionMode} == {
        "normal_query",
        "explicit_remember",
        "explicit_correct",
        "explicit_forget",
        "explicit_inspect",
        "ambiguous",
    }


def test_routing_decision_is_the_closed_spec_vocabulary():
    """`spec:370-372` fixes the three branches."""
    assert {member.value for member in RoutingDecision} == {
        "normal_query",
        "explicit_memory_action",
        "needs_clarification",
    }


def test_context_mode_exposes_all_four_values():
    """The vocabulary is complete from Stage 1 even though only two are reachable.

    `ADR 0039:54-66` — the planner exposes `none|rag_only|memory_only|both`, but
    only `none|rag_only` are reachable until governed Memory Read exists.
    """
    assert {member.value for member in ContextMode} == {
        "none",
        "rag_only",
        "memory_only",
        "both",
    }


def test_understanding_result_defaults_to_no_semantic_claims():
    """An ordinary query asserts nothing; the defaults must say so."""
    result = TurnUnderstandingResult(interaction_mode=InteractionMode.NORMAL_QUERY)

    assert result.topics == ()
    assert result.entities == ()
    assert result.current_assertions == ()
    assert result.current_overrides == ()
    assert result.requested_memory_keys == ()
    assert result.current_memory_override_keys == ()
    assert result.temporal_context is None
    assert result.needs_clarification is False
    assert result.reason_codes == ()


def test_understanding_result_is_frozen():
    result = TurnUnderstandingResult(interaction_mode=InteractionMode.NORMAL_QUERY)

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.needs_clarification = True  # type: ignore[misc]


def test_the_understanding_reason_codes_are_closed():
    """Free text cannot become a reason code; the vocabulary is the control."""
    assert {member.value for member in UnderstandingReason} == {
        "no_explicit_signal",
        "deterministic_match",
        "quoted_speech_act",
        "negated_speech_act",
        "ambiguous_speech_act",
        "mention_not_speech_act",
        "context_required",
        "context_missing",
        "inspect_capability_unavailable",
        "parser_failed_closed",
    }


def test_explicit_intent_decision_requires_an_authorization_flag():
    """The gate decides; there is no "maybe" that a caller could read as yes."""
    decision = ExplicitIntentDecision(
        authorized=True,
        reason_code=UnderstandingReason.DETERMINISTIC_MATCH,
    )

    assert decision.authorized is True
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.authorized = False  # type: ignore[misc]


def test_a_context_plan_separates_the_proposal_from_the_effective_mode():
    """The shadow-rollout invariant has to be representable, not implied.

    `plan v0.7:444-450` — the planner proposes, but while enforcement is disabled
    the effective normal-query source plan stays the existing `RAG_ONLY` baseline.
    """
    plan = ContextPlan(proposed=ContextMode.NONE, effective=ContextMode.RAG_ONLY)

    assert plan.proposed is ContextMode.NONE
    assert plan.effective is ContextMode.RAG_ONLY
    assert plan.is_shadow is True

    with pytest.raises(dataclasses.FrozenInstanceError):
        plan.effective = ContextMode.NONE  # type: ignore[misc]


def test_an_enforced_plan_is_not_shadow():
    plan = ContextPlan(proposed=ContextMode.RAG_ONLY, effective=ContextMode.RAG_ONLY)

    assert plan.is_shadow is False


def test_context_plan_defaults_to_empty_requested_memory_keys():
    plan = ContextPlan(proposed=ContextMode.RAG_ONLY, effective=ContextMode.RAG_ONLY)
    assert plan.requested_memory_keys == ()
