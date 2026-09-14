"""Positive family-specific source handling: proposal, record, and the gate.

Task 5 (`plan v0.6:408-483`, `spec:424-490`, `ADR 0038`) draws one boundary in
three places, and every test here is an attempt to cross it:

1. a **proposal** is typed evidence from orchestration and carries no authority;
2. a **record** is the durable authority object, and only the persistence seam
   may create one;
3. the **gate** turns records into permission, and it must say no to everything
   except one exact outcome.

The tests are deliberately written so that a permissive implementation cannot
pass by accident. `allows_background_formation(None)` is checked as well as
every explicit outcome, because "no record" is the state the old system treated
as permission (`ADR 0038:59`).

The import-boundary tests run in a fresh interpreter rather than reading source:
`Settings`-style capture and module-graph claims in this repository have been
wrong when reasoned about instead of measured, and a `sys.modules` snapshot is
the only thing that actually proves what an import drags in.
"""

from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingProposal,
    SourceHandlingProposalOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
    allows_background_formation,
    authority_key,
    propose_source_handling,
)

REPO_ROOT = Path(__file__).resolve().parents[4]

RECORDED_AT = datetime(2026, 9, 14, tzinfo=timezone.utc)

MESSAGE_ID = "msg_0123456789abcdef"
OUTBOX_ID = "out_0123456789abcdef"


def _record(
    outcome: SourceHandlingOutcome,
    *,
    family: MemoryFamily = MemoryFamily.SEMANTIC,
) -> SourceHandlingRecord:
    return SourceHandlingRecord(
        source_outbox_id=OUTBOX_ID,
        source_message_id=MESSAGE_ID,
        family=family,
        outcome=outcome,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=RECORDED_AT,
    )


# ---------------------------------------------------------------------------
# 1. The proposal truth table: reason -> outcome, all four reasons, closed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("reason", "expected"),
    [
        (
            SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
            SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE,
        ),
        (
            SourceHandlingReason.EXPLICIT_ACTION,
            SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        ),
        (
            SourceHandlingReason.AMBIGUOUS_INTENT,
            SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        ),
        (
            SourceHandlingReason.SENSITIVE_BLOCKED,
            SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        ),
    ],
)
def test_proposal_outcome_is_derived_from_the_reason(
    reason: SourceHandlingReason,
    expected: SourceHandlingProposalOutcome,
) -> None:
    """The reason determines the outcome; a caller cannot state them separately.

    `spec:440-445` fixes the mapping as a table. If the caller could pass an
    outcome as well, a call could claim `BACKGROUND_ELIGIBLE` while naming
    `EXPLICIT_ACTION`, and the two fields would disagree in the record that
    Stage 2 persists.
    """
    proposal = propose_source_handling(
        source_message_id=MESSAGE_ID,
        family=MemoryFamily.SEMANTIC,
        reason_code=reason,
    )

    assert proposal.outcome is expected
    assert proposal.reason_code is reason


def test_only_the_policy_eligible_reason_is_eligible() -> None:
    """Exactly one of the four reasons may propose background eligibility.

    Stated separately from the parametrized table because a permissive
    implementation that returned `BACKGROUND_ELIGIBLE` for everything would
    still satisfy four individual equalities only if the table were wrong; this
    asserts the count directly.
    """
    eligible = [
        reason
        for reason in SourceHandlingReason
        if propose_source_handling(
            source_message_id=MESSAGE_ID,
            family=MemoryFamily.SEMANTIC,
            reason_code=reason,
        ).outcome
        is SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE
    ]

    assert eligible == [SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE]


def test_ambiguous_explicit_and_sensitive_sources_are_blocked() -> None:
    """The three non-eligible readings are blocked, not merely non-eligible.

    `BACKGROUND_BLOCKED` is the proposal vocabulary's way of saying the source
    was *considered and refused*, which is different from the reason never
    having been produced (`plan v0.6:460-464`).
    """
    blocked = {
        reason: propose_source_handling(
            source_message_id=MESSAGE_ID,
            family=MemoryFamily.SEMANTIC,
            reason_code=reason,
        ).outcome
        for reason in (
            SourceHandlingReason.EXPLICIT_ACTION,
            SourceHandlingReason.AMBIGUOUS_INTENT,
            SourceHandlingReason.SENSITIVE_BLOCKED,
        )
    }

    assert set(blocked.values()) == {SourceHandlingProposalOutcome.BACKGROUND_BLOCKED}


#: Every reason/outcome pair the constructor may see, and whether it is the
#: consistent one. The full cross product, so a table that silently shrank is a
#: failure rather than a smaller test run.
_PROPOSAL_PAIRS = [
    (
        SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE,
        True,
    ),
    (
        SourceHandlingReason.EXPLICIT_ACTION,
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        True,
    ),
    (
        SourceHandlingReason.AMBIGUOUS_INTENT,
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        True,
    ),
    (
        SourceHandlingReason.SENSITIVE_BLOCKED,
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        True,
    ),
    (
        SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        SourceHandlingProposalOutcome.BACKGROUND_BLOCKED,
        False,
    ),
    (
        SourceHandlingReason.EXPLICIT_ACTION,
        SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE,
        False,
    ),
    (
        SourceHandlingReason.AMBIGUOUS_INTENT,
        SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE,
        False,
    ),
    (
        SourceHandlingReason.SENSITIVE_BLOCKED,
        SourceHandlingProposalOutcome.BACKGROUND_ELIGIBLE,
        False,
    ),
]


def test_the_constructor_pair_table_covers_every_combination() -> None:
    """Guard for the table below: four reasons times two outcomes, no gaps."""
    assert len(_PROPOSAL_PAIRS) == len(SourceHandlingReason) * len(
        SourceHandlingProposalOutcome
    )
    assert len({(reason, outcome) for reason, outcome, _ in _PROPOSAL_PAIRS}) == 8


@pytest.mark.parametrize(("reason", "outcome", "consistent"), _PROPOSAL_PAIRS)
def test_the_proposal_constructor_enforces_the_closed_mapping(
    reason: SourceHandlingReason,
    outcome: SourceHandlingProposalOutcome,
    consistent: bool,
) -> None:
    """The mapping is enforced at construction, not only by the factory.

    `propose_source_handling` derives the outcome and can never produce a
    contradiction, but the dataclass is public. Without a check here, a caller
    can build `BACKGROUND_ELIGIBLE` + `EXPLICIT_ACTION` by hand — a proposal
    that says "this source is safe to infer from" while naming the reason that
    says it was already handled explicitly. Stage 2 binds proposals to outbox
    rows, so a contradictory one would reach storage and read as permission.
    """
    if consistent:
        proposal = SourceHandlingProposal(
            source_message_id=MESSAGE_ID,
            family=MemoryFamily.SEMANTIC,
            outcome=outcome,
            reason_code=reason,
        )

        assert proposal.outcome is outcome
        assert proposal.reason_code is reason
    else:
        with pytest.raises(ValueError):
            SourceHandlingProposal(
                source_message_id=MESSAGE_ID,
                family=MemoryFamily.SEMANTIC,
                outcome=outcome,
                reason_code=reason,
            )


def test_the_factory_and_the_constructor_agree() -> None:
    """A factory-built proposal is exactly what the constructor accepts.

    If the two ever disagreed, the check would either reject the factory's own
    output or accept something the factory refuses to build.
    """
    for reason in SourceHandlingReason:
        proposal = propose_source_handling(
            source_message_id=MESSAGE_ID,
            family=MemoryFamily.SEMANTIC,
            reason_code=reason,
        )
        rebuilt = SourceHandlingProposal(
            source_message_id=proposal.source_message_id,
            family=proposal.family,
            outcome=proposal.outcome,
            reason_code=proposal.reason_code,
        )

        assert rebuilt == proposal


# ---------------------------------------------------------------------------
# 2. Stage-1 reachability: only the semantic family may be proposed for.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "family",
    [
        MemoryFamily.EPISODIC,
        MemoryFamily.WORKING,
        MemoryFamily.PROCEDURAL,
    ],
)
def test_a_non_semantic_family_cannot_receive_a_stage_one_proposal(
    family: MemoryFamily,
) -> None:
    """The other families are vocabulary until their own evaluated stage.

    `plan v0.6:465-467`: Stage 1 proposes only for `SEMANTIC`. This refuses the
    call rather than silently downgrading it, because a downgrade would have to
    keep a reason (`BACKGROUND_POLICY_ELIGIBLE`) that no longer matches its
    outcome, and the closed mapping above forbids that pair.
    """
    with pytest.raises(ValueError):
        propose_source_handling(
            source_message_id=MESSAGE_ID,
            family=family,
            reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        )


def test_the_semantic_family_is_the_only_stage_one_proposable_family() -> None:
    """A guard for the previous test: it must not be refusing everything."""
    proposal = propose_source_handling(
        source_message_id=MESSAGE_ID,
        family=MemoryFamily.SEMANTIC,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
    )

    assert proposal.family is MemoryFamily.SEMANTIC


# ---------------------------------------------------------------------------
# 3. The gate: absence denies, every explicit outcome denies, one passes.
# ---------------------------------------------------------------------------


def test_a_missing_record_is_unhandled_and_denies() -> None:
    """Absence is the state the architecture exists to stop trusting.

    `ADR 0038:59`: "Absence of a record means `UNHANDLED`. It never means
    permission." `UNHANDLED` is deliberately not an enum member
    (`spec:475-477`), so the deny is expressed by the predicate refusing
    `None` rather than by a member being checked.
    """
    assert allows_background_formation(None) is False


@pytest.mark.parametrize(
    "outcome",
    [
        SourceHandlingOutcome.EXPLICIT_APPLIED,
        SourceHandlingOutcome.EXPLICIT_REFUSED,
        SourceHandlingOutcome.EXPLICIT_NOOP,
        SourceHandlingOutcome.FORGET_APPLIED,
        SourceHandlingOutcome.FORGET_REFUSED,
    ],
)
def test_every_explicit_authoritative_outcome_fails_the_gate(
    outcome: SourceHandlingOutcome,
) -> None:
    """An explicit handling of a source cannot double as inference permission.

    `ADR 0038` Validation 2 and `plan v0.6:468-470`. This is the property that
    stops one source being counted both as an explicit user command and as
    independent background evidence.
    """
    assert allows_background_formation(_record(outcome)) is False


def test_only_background_eligible_passes_the_gate() -> None:
    """The single positive outcome, and the single reason it exists."""
    assert (
        allows_background_formation(_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE))
        is True
    )


def test_the_gate_is_an_identity_check_not_a_truthiness_check() -> None:
    """A record whose outcome merely *looks* eligible must not pass.

    Two impostors, because they fail for different reasons and a gate can be
    wrong in either direction:

    - a stand-in carrying the *string* `"background_eligible"` catches a gate
      that compares by value;
    - a stand-in carrying the *real enum member* catches a gate that checks the
      outcome but never checks that the thing holding it is a record at all.

    Only the second one proves the type check is load-bearing, which is why it
    is here: without it, deleting `isinstance` leaves every test green.
    """
    record = _record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE)

    assert record.outcome is SourceHandlingOutcome.BACKGROUND_ELIGIBLE
    assert allows_background_formation(record) is True

    class _StringImpostor:
        """Duck-typed stand-in carrying the same string value."""

        outcome = "background_eligible"

    class _EnumImpostor:
        """Duck-typed stand-in carrying the genuine enum member."""

        outcome = SourceHandlingOutcome.BACKGROUND_ELIGIBLE

    assert allows_background_formation(_StringImpostor()) is False  # type: ignore[arg-type]
    assert allows_background_formation(_EnumImpostor()) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 4. The contracts are closed and immutable.
# ---------------------------------------------------------------------------


def test_the_family_vocabulary_is_exactly_four_values() -> None:
    """`spec:244-254` names four families; the enum is the whole vocabulary."""
    assert {family.value for family in MemoryFamily} == {
        "semantic",
        "episodic",
        "working",
        "procedural",
    }


def test_the_proposal_outcome_vocabulary_is_exactly_two_values() -> None:
    """A proposal can only say eligible or blocked."""
    assert {outcome.value for outcome in SourceHandlingProposalOutcome} == {
        "background_eligible",
        "background_blocked",
    }


def test_the_reason_vocabulary_is_exactly_four_values() -> None:
    """Reasons are closed so a log line or model prose cannot become one."""
    assert {reason.value for reason in SourceHandlingReason} == {
        "explicit_action",
        "background_policy_eligible",
        "ambiguous_intent",
        "sensitive_blocked",
    }


def test_the_authoritative_outcome_vocabulary_is_exactly_six_values() -> None:
    """`spec:466-473`: one positive outcome plus five explicit/forget ones."""
    assert {outcome.value for outcome in SourceHandlingOutcome} == {
        "background_eligible",
        "explicit_applied",
        "explicit_refused",
        "explicit_noop",
        "forget_applied",
        "forget_refused",
    }


def test_background_blocked_is_not_an_authoritative_outcome() -> None:
    """`BACKGROUND_BLOCKED` is proposal-only (`spec:447-449`).

    It must be impossible to persist one, so the authoritative vocabulary must
    not contain the member at all. A shared enum between proposal and record
    would make this unrepresentable.
    """
    assert not hasattr(SourceHandlingOutcome, "BACKGROUND_BLOCKED")
    assert "background_blocked" not in {
        outcome.value for outcome in SourceHandlingOutcome
    }


def test_a_proposal_carries_no_storage_identity_and_no_timestamp() -> None:
    """The proposal's field set is the contract (`spec:429-435`).

    `source_outbox_id` is storage identity. If it were optional here, a caller
    could start populating it from orchestration and quietly move the
    Stage-2 binding boundary forward.
    """
    proposal = propose_source_handling(
        source_message_id=MESSAGE_ID,
        family=MemoryFamily.SEMANTIC,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
    )

    assert {field.name for field in dataclasses.fields(proposal)} == {
        "source_message_id",
        "family",
        "outcome",
        "reason_code",
    }


def test_a_record_carries_the_storage_identity_and_the_timestamp() -> None:
    """The authority object is the one that names the outbox row."""
    assert {field.name for field in dataclasses.fields(SourceHandlingRecord)} == {
        "source_outbox_id",
        "source_message_id",
        "family",
        "outcome",
        "reason_code",
        "recorded_at",
    }


@pytest.mark.parametrize("field_name", ["family", "outcome", "reason_code"])
def test_a_record_rejects_an_unknown_vocabulary_value(field_name: str) -> None:
    """A closed vocabulary that accepts any string is not closed.

    Persistence in Stage 2 reads these back from storage, so an unknown value
    must fail at construction rather than travel through the domain as free
    text.
    """
    values = {
        "source_outbox_id": OUTBOX_ID,
        "source_message_id": MESSAGE_ID,
        "family": MemoryFamily.SEMANTIC,
        "outcome": SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        "reason_code": SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        "recorded_at": RECORDED_AT,
    }
    values[field_name] = "not_a_real_member"

    with pytest.raises(ValueError):
        SourceHandlingRecord(**values)  # type: ignore[arg-type]


def test_a_record_rejects_an_empty_identity() -> None:
    """The uniqueness boundary is only meaningful with real identities."""
    with pytest.raises(ValueError):
        SourceHandlingRecord(
            source_outbox_id="",
            source_message_id=MESSAGE_ID,
            family=MemoryFamily.SEMANTIC,
            outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
            reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
            recorded_at=RECORDED_AT,
        )


def test_a_record_rejects_a_naive_timestamp() -> None:
    """A durable record's time must be unambiguous.

    `SourceHandlingRecord` becomes a persisted row in Task 6, and the existing
    durable Memory domain already refuses a naive datetime and normalises to UTC
    (`write_pipeline/models.py:156-161`). A naive value here would be written as
    local time by whatever host happened to build it, so two records from two
    hosts could not be ordered. This is the same contract, applied before the
    record exists rather than after it is stored.
    """
    with pytest.raises(ValueError):
        SourceHandlingRecord(
            source_outbox_id=OUTBOX_ID,
            source_message_id=MESSAGE_ID,
            family=MemoryFamily.SEMANTIC,
            outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
            reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
            recorded_at=datetime(2026, 9, 14),
        )


def test_a_record_normalizes_an_aware_timestamp_to_utc() -> None:
    """Any aware timestamp is accepted and stored as the same instant in UTC.

    Accepting the input but keeping its original offset would make equality and
    ordering depend on which zone the writer used, so the value is normalised
    rather than merely validated.
    """
    bangkok = timezone(timedelta(hours=7))

    record = SourceHandlingRecord(
        source_outbox_id=OUTBOX_ID,
        source_message_id=MESSAGE_ID,
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=datetime(2026, 9, 14, 12, 30, tzinfo=bangkok),
    )

    assert record.recorded_at == datetime(2026, 9, 14, 5, 30, tzinfo=timezone.utc)
    assert record.recorded_at.utcoffset() == timedelta(0)


def test_the_contracts_are_immutable() -> None:
    """Frozen dataclasses: a decision record cannot be edited after the fact."""
    proposal = propose_source_handling(
        source_message_id=MESSAGE_ID,
        family=MemoryFamily.SEMANTIC,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
    )

    with pytest.raises(dataclasses.FrozenInstanceError):
        proposal.outcome = SourceHandlingProposalOutcome.BACKGROUND_BLOCKED  # type: ignore[misc]

    with pytest.raises(dataclasses.FrozenInstanceError):
        _record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE).outcome = (  # type: ignore[misc]
            SourceHandlingOutcome.EXPLICIT_APPLIED
        )


def test_the_authority_key_is_the_outbox_identity_and_the_family() -> None:
    """`(source_outbox_id, family)` is the durable uniqueness boundary.

    `spec:479-482`. Defined here as a pure function so Stage 2 can key on it
    without either module re-deriving the tuple from field order.
    """
    record = _record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE)

    assert authority_key(record) == (OUTBOX_ID, MemoryFamily.SEMANTIC)


def test_two_families_for_one_outbox_row_are_distinct_authorities() -> None:
    """One source event may be handled once per family, not once in total."""
    semantic = authority_key(_record(SourceHandlingOutcome.BACKGROUND_ELIGIBLE))
    episodic = authority_key(
        _record(
            SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
            family=MemoryFamily.EPISODIC,
        )
    )

    assert semantic != episodic


# ---------------------------------------------------------------------------
# 5. Import boundary, measured in a fresh interpreter.
# ---------------------------------------------------------------------------


_HEAVY_ROOTS = ("fastapi", "starlette", "sqlalchemy", "chromadb", "torch")

# The heavy-root tuple is substituted textually, not with `str.format`: the probe
# bodies contain set comprehensions, whose braces `format` would read as fields.
_SOURCE_HANDLING_PROBE = """
import sys
import backend.memory.source_handling  # noqa: F401
heavy = sorted({name.split(".")[0] for name in sys.modules} & set(__HEAVY_ROOTS__))
print("HEAVY=" + ",".join(heavy))
print(
    "WRITE_PIPELINE="
    + str(any(n.startswith("backend.memory.write_pipeline") for n in sys.modules))
)
"""

_ORCHESTRATION_PROBE = """
import sys
import backend.orchestration.conversation_orchestrator  # noqa: F401
heavy = sorted({name.split(".")[0] for name in sys.modules} & set(__HEAVY_ROOTS__))
print("HEAVY=" + ",".join(heavy))
print(
    "WRITE_PIPELINE="
    + str(any(n.startswith("backend.memory.write_pipeline") for n in sys.modules))
)
print("SOURCE_HANDLING=" + str("backend.memory.source_handling" in sys.modules))
"""


def _probe(template: str) -> dict[str, str]:
    """Import one module in a fresh interpreter and report what came with it."""
    source = template.replace("__HEAVY_ROOTS__", repr(_HEAVY_ROOTS))
    result = subprocess.run(
        [sys.executable, "-c", source],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": "."},
    )
    assert result.returncode == 0, result.stderr[-800:]

    return dict(line.split("=", 1) for line in result.stdout.strip().splitlines())


def test_source_handling_imports_nothing_heavy() -> None:
    """It is a vocabulary and a predicate; it needs the standard library.

    `plan v0.6:456-459`. `backend.memory.write_pipeline` is not merely heavy —
    importing it executes `backend.memory.write_pipeline.__init__`, which pulls
    `backend.security`, which pulls FastAPI. That is why this module lives at
    the `backend.memory` root and not inside the write pipeline.
    """
    report = _probe(_SOURCE_HANDLING_PROBE)

    assert report["HEAVY"] == ""
    assert report["WRITE_PIPELINE"] == "False"


def test_orchestration_does_not_pull_the_write_pipeline_in() -> None:
    """Orchestration may consume the vocabulary without acquiring persistence.

    The orchestrator is a domain module, and `spec:555` forbids domain modules
    from importing SQLAlchemy, FastAPI, or provider SDKs. It currently imports
    nothing from `backend.memory` at all; Task 5 adds exactly one lightweight
    import and must not add the package that would undo that.
    """
    report = _probe(_ORCHESTRATION_PROBE)

    assert report["HEAVY"] == ""
    assert report["WRITE_PIPELINE"] == "False"
    assert report["SOURCE_HANDLING"] == "True"
