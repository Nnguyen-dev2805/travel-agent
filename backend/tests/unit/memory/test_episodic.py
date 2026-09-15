"""Episodic Memory vertical slice — grounding, authority, activation, read.

Plan v0.20 Task 12 Step 1. Every case the plan names as required is pinned here
before the implementation exists, so a green run means the slice satisfies the
contract rather than that the tests were written to match it.

The load-bearing rule is that an episode is *grounded*: actor, event, time and
provenance are all required, and missing any one of them refuses formation and
activation. There is deliberately no universal event ontology here — `event` is a
bounded string, not a closed vocabulary, because inventing one would be the
speculative family modelling the plan forbids.
"""

from datetime import datetime, timedelta, timezone

import pytest

from backend.memory.episodic import (
    EpisodeAbstentionReason,
    EpisodeActivationFacts,
    EpisodeActivationPolicy,
    EpisodeActivationReason,
    EpisodeCandidate,
    EpisodeFormationEngine,
    EpisodeGrounding,
    EpisodeProvenance,
    EpisodeReadRequest,
    EpisodeRefusalReason,
    EpisodicReadEngine,
    SelectedEpisode,
    StoredEpisodeRow,
    validate_episode_grounding,
)
from backend.memory.lifecycle import RetentionAssignmentPolicy, SourceValidity
from backend.memory.source_handling import (
    MemoryFamily,
    SourceHandlingOutcome,
    SourceHandlingReason,
    SourceHandlingRecord,
)
from backend.memory.write_pipeline.models import (
    MemoryScope,
    RetentionMode,
    SensitivityBand,
    VersionStatus,
)

NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)


def _provenance() -> EpisodeProvenance:
    return EpisodeProvenance(source_outbox_id="cout_1", source_message_id="msg_1")


def _grounded(**overrides) -> EpisodeGrounding:
    values = {
        "actor": "user_1",
        "event": "rejected Da Nang for the winter trip over rain concerns",
        "occurred_at": NOW,
        "provenance": _provenance(),
    }
    values.update(overrides)
    return EpisodeGrounding(**values)


def _episodic_record(outcome: SourceHandlingOutcome) -> SourceHandlingRecord:
    reason = (
        SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE
        if outcome is SourceHandlingOutcome.BACKGROUND_ELIGIBLE
        else SourceHandlingReason.EXPLICIT_ACTION
    )
    return SourceHandlingRecord(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        family=MemoryFamily.EPISODIC,
        outcome=outcome,
        reason_code=reason,
        recorded_at=NOW,
    )


def _semantic_record() -> SourceHandlingRecord:
    return SourceHandlingRecord(
        source_outbox_id="cout_1",
        source_message_id="msg_1",
        family=MemoryFamily.SEMANTIC,
        outcome=SourceHandlingOutcome.BACKGROUND_ELIGIBLE,
        reason_code=SourceHandlingReason.BACKGROUND_POLICY_ELIGIBLE,
        recorded_at=NOW,
    )


def _form(**overrides):
    engine = EpisodeFormationEngine()
    kwargs = {
        "source_outbox_id": "cout_1",
        "source_message_id": "msg_1",
        "owner_user_id": "user_1",
        "conversation_id": "conv_1",
        "grounding": _grounded(),
        "source_handling_record": _episodic_record(
            SourceHandlingOutcome.BACKGROUND_ELIGIBLE
        ),
    }
    kwargs.update(overrides)
    return engine.form_episode(**kwargs)


# --- Grounding: every required fact is required -----------------------------


def test_a_fully_grounded_event_is_accepted():
    assert validate_episode_grounding(_grounded()) is None


def test_a_missing_actor_is_refused():
    assert (
        validate_episode_grounding(_grounded(actor=""))
        is EpisodeRefusalReason.MISSING_ACTOR
    )


def test_a_missing_event_is_refused():
    assert (
        validate_episode_grounding(_grounded(event=""))
        is EpisodeRefusalReason.MISSING_EVENT
    )


def test_a_missing_time_is_refused():
    assert (
        validate_episode_grounding(_grounded(occurred_at=None))
        is EpisodeRefusalReason.MISSING_TIME
    )


def test_a_timezone_naive_time_is_refused():
    """A naive datetime is not an instant, so it cannot ground an event."""
    naive = datetime(2026, 9, 15, 12, 0)
    assert (
        validate_episode_grounding(_grounded(occurred_at=naive))
        is EpisodeRefusalReason.INVALID_TIME
    )


def test_a_non_datetime_time_is_refused():
    assert (
        validate_episode_grounding(_grounded(occurred_at="2026-09-15T12:00:00Z"))
        is EpisodeRefusalReason.INVALID_TIME
    )


def test_missing_provenance_is_refused():
    assert (
        validate_episode_grounding(_grounded(provenance=None))
        is EpisodeRefusalReason.MISSING_PROVENANCE
    )


def test_a_provenance_without_a_source_outbox_identity_is_refused():
    assert (
        validate_episode_grounding(
            _grounded(provenance=EpisodeProvenance("", "msg_1"))
        )
        is EpisodeRefusalReason.INVALID_PROVENANCE
    )


# --- Formation authority: positive episodic handling, nothing else ----------


def test_formation_refuses_an_unhandled_source():
    """No persisted record is `UNHANDLED`, which grants nothing (ADR 0038:59)."""
    assert _form(source_handling_record=None) is None


def test_formation_refuses_a_semantic_family_record():
    """Semantic authority cannot be reused as episodic authority."""
    assert _form(source_handling_record=_semantic_record()) is None


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
def test_formation_refuses_a_non_eligible_episodic_outcome(outcome):
    assert _form(source_handling_record=_episodic_record(outcome)) is None


def test_formation_refuses_incomplete_grounding_even_with_authority():
    assert _form(grounding=_grounded(actor="")) is None


def test_formation_accepts_a_grounded_event_with_positive_episodic_handling():
    candidate = _form()
    assert isinstance(candidate, EpisodeCandidate)
    assert candidate.grounding.actor == "user_1"
    assert candidate.conversation_id == "conv_1"


def test_formation_assigns_retention_through_the_shared_retention_owner():
    """Retention is `RetentionAssignmentPolicy`'s decision, not episodic's."""
    expected = RetentionAssignmentPolicy().assign(
        scope=MemoryScope.CONVERSATION, authority=candidate_authority()
    )
    assert _form().retention_mode is expected


def candidate_authority():
    from backend.memory.write_pipeline.models import Authority

    return Authority.REPEATED_INFERENCE


def test_formation_refuses_a_stale_suppression_generation():
    """Work stamped with an older generation cannot form (ADR 0037)."""
    assert _form(stamped_generation=1, current_generation=2) is None


def test_formation_refuses_an_invalid_source():
    assert _form(source_validity=SourceValidity.INVALID) is None


def test_formation_refuses_an_expired_retention_window():
    expired = NOW - timedelta(days=1)
    assert _form(expires_at=expired, observed_at=NOW) is None


def test_formation_refuses_a_prohibited_secret_before_any_model_exposure():
    """The detector's auth pattern is `password[:=]<value>`; the shape matters."""
    assert _form(secret_scan_text="password=hunter2") is None


def test_a_duplicate_source_keeps_one_provenance_identity():
    """Redelivery of one source is the same provenance, so it adds no support."""
    first = _form()
    second = _form()
    assert first.provenance_identity() == second.provenance_identity()


# --- Activation: the episodic gate is separate and default-off --------------


def _activation_facts(**overrides) -> EpisodeActivationFacts:
    values = {
        "grounding_conclusive": True,
        "lifecycle_eligible": True,
        "source_validity": SourceValidity.VALID,
        "stamped_generation": 1,
        "current_generation": 1,
        "has_unresolved_conflict": False,
    }
    values.update(overrides)
    return EpisodeActivationFacts(**values)


def test_the_episodic_gate_is_off_by_default():
    decision = EpisodeActivationPolicy().evaluate(_activation_facts())
    assert decision.eligible is False
    assert decision.target_status is VersionStatus.SHADOW
    assert decision.reason is EpisodeActivationReason.EPISODIC_GATE_DISABLED


def test_an_inconclusive_episodic_gate_cannot_activate():
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(episodic_gate_enabled=True)
    )
    assert decision.reason is EpisodeActivationReason.EPISODIC_GATE_INCONCLUSIVE


def test_one_grounded_event_activates_when_the_episodic_gate_passes():
    """No 2-turn/3-evidence threshold: one independently grounded event suffices."""
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(episodic_gate_enabled=True, episodic_gate_conclusive=True)
    )
    assert decision.eligible is True
    assert decision.target_status is VersionStatus.ACTIVE
    assert decision.reason is EpisodeActivationReason.ELIGIBLE_ACTIVE


def test_incomplete_grounding_cannot_activate():
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(
            grounding_conclusive=False,
            episodic_gate_enabled=True,
            episodic_gate_conclusive=True,
        )
    )
    assert decision.reason is EpisodeActivationReason.GROUNDING_INCOMPLETE


def test_a_lifecycle_denial_cannot_activate():
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(
            lifecycle_eligible=False,
            episodic_gate_enabled=True,
            episodic_gate_conclusive=True,
        )
    )
    assert decision.reason is EpisodeActivationReason.LIFECYCLE_DENIED


def test_an_unresolved_conflict_cannot_activate():
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(
            has_unresolved_conflict=True,
            episodic_gate_enabled=True,
            episodic_gate_conclusive=True,
        )
    )
    assert decision.reason is EpisodeActivationReason.UNRESOLVED_CONFLICT


def test_a_stale_generation_cannot_activate():
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(
            stamped_generation=1,
            current_generation=2,
            episodic_gate_enabled=True,
            episodic_gate_conclusive=True,
        )
    )
    assert decision.reason is EpisodeActivationReason.STALE_GENERATION


def test_an_invalid_source_cannot_activate():
    decision = EpisodeActivationPolicy().evaluate(
        _activation_facts(
            source_validity=SourceValidity.INVALID,
            episodic_gate_enabled=True,
            episodic_gate_conclusive=True,
        )
    )
    assert decision.reason is EpisodeActivationReason.SOURCE_INVALID


# --- Read: exact typed filters, and abstention rather than a near match -----


class _FakeEpisodeStore:
    def __init__(self, rows=()):
        self.rows = tuple(rows)
        self.requests = []

    def list_storage_scoped(self, request):
        self.requests.append(request)
        return self.rows


def _row(**overrides) -> StoredEpisodeRow:
    values = {
        "episode_id": "ep_1",
        "owner_user_id": "user_1",
        "conversation_id": "conv_1",
        "actor": "user_1",
        "event": "rejected Da Nang for the winter trip over rain concerns",
        "occurred_at": NOW,
        "source_message_id": "msg_1",
        "source_outbox_id": "cout_1",
        "retention_mode": RetentionMode.CONVERSATION_BOUND,
        "stamped_generation": 1,
        "current_generation": 1,
        "status": VersionStatus.ACTIVE,
        "sensitivity": SensitivityBand.ORDINARY_PERSONAL,
        "source_validity": SourceValidity.VALID,
    }
    values.update(overrides)
    return StoredEpisodeRow(**values)


def _read_request(**overrides) -> EpisodeReadRequest:
    values = {
        "owner_user_id": "user_1",
        "conversation_id": "conv_1",
        "occurred_after": NOW - timedelta(days=30),
        "occurred_before": NOW + timedelta(days=1),
    }
    values.update(overrides)
    return EpisodeReadRequest(**values)


def test_a_relevant_grounded_episode_is_selected():
    selection = EpisodicReadEngine(_FakeEpisodeStore([_row()])).select(_read_request())
    assert len(selection.selected) == 1
    assert isinstance(selection.selected[0], SelectedEpisode)
    assert selection.selected[0].episode_id == "ep_1"


def test_a_request_without_a_grounded_filter_abstains():
    selection = EpisodicReadEngine(_FakeEpisodeStore([_row()])).select(
        _read_request(occurred_after=None, occurred_before=None)
    )
    assert selection.selected == ()
    assert selection.abstention_reason is EpisodeAbstentionReason.NO_GROUNDED_FILTER


def test_an_unrelated_query_abstains_rather_than_returning_a_near_match():
    """A window that excludes the only episode abstains; it does not widen."""
    selection = EpisodicReadEngine(_FakeEpisodeStore([_row()])).select(
        _read_request(
            occurred_after=NOW + timedelta(days=10),
            occurred_before=NOW + timedelta(days=20),
        )
    )
    assert selection.selected == ()
    assert selection.abstention_reason is EpisodeAbstentionReason.NO_ELIGIBLE_EPISODE


def test_another_owners_episode_is_never_selected():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(owner_user_id="user_2")])
    ).select(_read_request())
    assert selection.selected == ()


def test_another_conversations_episode_is_not_selected_for_a_conversation_scope():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(conversation_id="conv_2")])
    ).select(_read_request())
    assert selection.selected == ()


def test_a_non_active_episode_is_not_selected():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(status=VersionStatus.SHADOW)])
    ).select(_read_request())
    assert selection.selected == ()


def test_a_stale_generation_episode_is_not_selected():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(stamped_generation=1, current_generation=2)])
    ).select(_read_request())
    assert selection.selected == ()


def test_an_expired_episode_is_not_selected():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(expires_at=NOW - timedelta(days=1))])
    ).select(_read_request())
    assert selection.selected == ()


def test_an_invalid_source_episode_is_not_selected():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(source_validity=SourceValidity.INVALID)])
    ).select(_read_request())
    assert selection.selected == ()


def test_an_unresolved_conflict_episode_is_not_selected():
    selection = EpisodicReadEngine(
        _FakeEpisodeStore([_row(unresolved_conflict=True)])
    ).select(_read_request())
    assert selection.selected == ()


def test_selection_is_bounded():
    rows = [_row(episode_id=f"ep_{i}", occurred_at=NOW - timedelta(hours=i)) for i in range(20)]
    selection = EpisodicReadEngine(_FakeEpisodeStore(rows)).select(
        _read_request(max_selected=3)
    )
    assert len(selection.selected) == 3


def test_selection_is_deterministic_most_recent_first():
    rows = [
        _row(episode_id="older", occurred_at=NOW - timedelta(days=2)),
        _row(episode_id="newer", occurred_at=NOW - timedelta(hours=1)),
    ]
    selection = EpisodicReadEngine(_FakeEpisodeStore(rows)).select(_read_request())
    assert [e.episode_id for e in selection.selected] == ["newer", "older"]
