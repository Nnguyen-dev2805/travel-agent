"""Unit tests for deterministic rule-based memory extraction.

The extractor is a pure text-to-draft function: it copies provenance and
trace fields from the source message, proposes scope/type/confidence, and
never assigns a policy status. Trace and role enforcement belongs to the
policy, which the pipeline test below exercises end to end.

No test here touches a database, a model provider, Chroma, or the network.
"""

from datetime import datetime, timezone

from backend.memory.extraction import (
    EXTRACTOR_ID,
    MemoryExtractor,
    RuleBasedMemoryExtractor,
)
from backend.memory.models import (
    MemoryCandidateStatus,
    MemoryScope,
    MemorySourceMessage,
    MemoryType,
    PolicyReason,
    SensitivityLabel,
)
from backend.memory.policy import MemoryPolicy

MOMENT = datetime(2026, 9, 4, 12, 0, 0, tzinfo=timezone.utc)

PREFERENCE_TEXT = "Tôi ăn chay trường, hãy nhớ giúp tôi."
CONSTRAINT_TEXT = "Ngân sách chuyến này tối đa 20 triệu."
CORRECTION_TEXT = "Thực ra tôi đổi sang đi tàu hỏa, sửa lại giúp tôi."
NO_SIGNAL_TEXT = "Hôm nay trời đẹp quá."
SECRET_TEXT = "API key của tôi là sk-test-AbC123xYz, đừng quên nhé."
EXCLUDED_TEXT = "Tôi thích đi biển."


def _message(content: str, **overrides) -> MemorySourceMessage:
    payload = {
        "message_id": "ms_example",
        "conversation_id": "cv_example",
        "workspace_id": "tw_example",
        "sequence": 1,
        "role": "user",
        "source": "ui",
        "trace_visibility": "included",
        "content": content,
        "created_at": MOMENT,
    }
    payload.update(overrides)
    return MemorySourceMessage(**payload)


def _extract(content: str, **overrides):
    return RuleBasedMemoryExtractor().extract([_message(content, **overrides)])


# 1. Governed fixture phrases produce governed drafts.


def test_preference_message_proposes_user_preference():
    (draft,) = _extract(PREFERENCE_TEXT)
    assert draft.proposed_scope is MemoryScope.USER
    assert draft.proposed_type is MemoryType.PREFERENCE
    assert draft.sensitivity_label is SensitivityLabel.NONE


def test_constraint_message_proposes_workspace_constraint():
    (draft,) = _extract(CONSTRAINT_TEXT)
    assert draft.proposed_scope is MemoryScope.WORKSPACE
    assert draft.proposed_type is MemoryType.CONSTRAINT


def test_correction_message_proposes_correction():
    (draft,) = _extract(CORRECTION_TEXT)
    assert draft.proposed_type is MemoryType.CORRECTION


def test_no_signal_message_proposes_none():
    (draft,) = _extract(NO_SIGNAL_TEXT)
    assert draft.proposed_scope is MemoryScope.NONE
    assert draft.proposed_type is MemoryType.NONE


def test_secret_like_content_is_marked_secret_and_redacted():
    (draft,) = _extract(SECRET_TEXT)
    assert draft.sensitivity_label is SensitivityLabel.SECRET
    assert "sk-test-AbC123xYz" not in draft.text
    assert "sk-test-AbC123xYz" not in draft.evidence_summary


# 2. Provenance and trace fields survive extraction untouched.


def test_drafts_preserve_provenance_and_trace_fields():
    for content in (
        PREFERENCE_TEXT,
        CONSTRAINT_TEXT,
        CORRECTION_TEXT,
        NO_SIGNAL_TEXT,
        SECRET_TEXT,
    ):
        (draft,) = _extract(content)
        assert draft.source_message_id == "ms_example"
        assert draft.conversation_id == "cv_example"
        assert draft.workspace_id == "tw_example"
        assert draft.source_sequence == 1
        assert draft.role == "user"
        assert draft.source == "ui"
        assert draft.trace_visibility == "included"


def test_extractor_never_marks_a_status():
    for content in (
        PREFERENCE_TEXT,
        CONSTRAINT_TEXT,
        CORRECTION_TEXT,
        NO_SIGNAL_TEXT,
        SECRET_TEXT,
    ):
        drafts = _extract(content)
        assert drafts
        for draft in drafts:
            assert draft.status is None
            assert draft.reason is None


# 3. Excluded ordinary chat messages cannot become accepted candidates.


def test_excluded_trace_message_produces_no_accepted_candidate():
    policy = MemoryPolicy()
    drafts = _extract(EXCLUDED_TEXT, trace_visibility="excluded")
    assert drafts
    decided = [policy.evaluate(draft) for draft in drafts]
    assert all(item.status is not MemoryCandidateStatus.ACCEPTED for item in decided)


# 4. Determinism and multi-signal coverage.


def test_extraction_is_deterministic():
    first = _extract(PREFERENCE_TEXT)
    second = _extract(PREFERENCE_TEXT)
    assert first == second


def test_message_with_two_signals_produces_two_drafts():
    drafts = _extract(
        "Thực ra tôi đổi sang đi tàu hỏa. Ngân sách chuyến này tối đa 20 triệu."
    )
    assert {draft.proposed_type for draft in drafts} == {
        MemoryType.CORRECTION,
        MemoryType.CONSTRAINT,
    }


def test_hedged_preference_gets_below_accept_confidence():
    (draft,) = _extract("Có lẽ tôi thích đi biển, nhưng chưa chắc đâu.")
    assert draft.proposed_scope is MemoryScope.USER
    assert draft.proposed_type is MemoryType.PREFERENCE
    assert draft.confidence == 0.6
    decided = MemoryPolicy().evaluate(draft)
    assert decided.reason is PolicyReason.AMBIGUOUS


def test_chat_local_preference_is_conversation_scoped():
    (draft,) = _extract("Trong chat này thì tôi thích đi biển.")
    assert draft.proposed_scope is MemoryScope.CONVERSATION
    assert draft.proposed_type is MemoryType.PREFERENCE
    decided = MemoryPolicy().evaluate(draft)
    assert decided.reason is PolicyReason.WRONG_SCOPE


_CO_OCCURRENCE_CASES = [
    "API key của tôi là sk-live-PersistProbe9 và tôi thích ăn chay.",
    "password: hunter2x, ngân sách chuyến này tối đa 20 triệu.",
    "token = abcxyz9, thực ra tôi đổi sang đi tàu hỏa.",
]


def test_secret_co_occurrence_marks_every_draft_secret():
    for content in _CO_OCCURRENCE_CASES:
        drafts = _extract(content)
        assert len(drafts) == 2
        for draft in drafts:
            assert draft.sensitivity_label is SensitivityLabel.SECRET


def test_secret_co_occurrence_leaks_no_raw_secret():
    for content in _CO_OCCURRENCE_CASES:
        for draft in _extract(content):
            assert "PersistProbe9" not in draft.text
            assert "hunter2x" not in draft.text
            assert "abcxyz9" not in draft.text
            assert "PersistProbe9" not in draft.evidence_summary
            assert "hunter2x" not in draft.evidence_summary
            assert "abcxyz9" not in draft.evidence_summary


def test_secret_co_occurrence_produces_no_accepted_candidate():
    policy = MemoryPolicy()
    for content in _CO_OCCURRENCE_CASES:
        decided = [policy.evaluate(draft) for draft in _extract(content)]
        assert decided
        assert all(item.status is MemoryCandidateStatus.REJECTED for item in decided)
        assert all(item.reason is PolicyReason.SECRET_LIKE for item in decided)


def test_evidence_summary_carries_no_message_content():
    (draft,) = _extract(PREFERENCE_TEXT)
    assert draft.evidence_summary == "signal=preference:ăn chay"
    assert PREFERENCE_TEXT not in draft.evidence_summary
    (secret_draft,) = _extract(SECRET_TEXT)
    assert secret_draft.evidence_summary == "secret-like pattern redacted"


def test_extractor_contract_and_identity():
    assert isinstance(RuleBasedMemoryExtractor(), MemoryExtractor)
    assert EXTRACTOR_ID == "rule-based-v1"


def test_empty_content_produces_no_signal_draft():
    drafts = RuleBasedMemoryExtractor().extract([])
    assert drafts == ()
