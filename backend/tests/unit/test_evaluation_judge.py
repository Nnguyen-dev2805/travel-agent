"""Tests for strict answer-quality evaluation judge and invalid response handling.

Per the approved RAG repair plan (Task 4 Step 1 & 3):
- Single-answer judge contract scoring against question, evidence, and reference answer.
- Six exact D5 dimensions: groundedness, answer_relevance, correctness,
  completeness, practical_usefulness, clarity.
- Strict rejection of invalid provider responses (malformed JSON, missing
  dimension, out-of-range scores 0/6, wrong types, empty response, provider exception).
- Invalid responses produce judge_valid=False, failure_label="judge_invalid",
  and no numeric dimension scores.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock
import pytest

from backend.rag.contracts import RetrievalResult
from backend.rag.evaluation.models import JudgeConfig
from backend.rag.evaluation.judge import (
    JUDGE_DIMENSIONS,
    JUDGE_PROMPT_ID,
    JUDGE_RUBRIC_ID,
    JUDGE_SCHEMA_VERSION,
    JudgeAdapter,
    JudgeResult,
)


@pytest.fixture
def judge_config() -> JudgeConfig:
    return JudgeConfig(
        model="gpt-4o-mini",
        prompt_id=JUDGE_PROMPT_ID,
        rubric_id=JUDGE_RUBRIC_ID,
        schema_version=JUDGE_SCHEMA_VERSION,
        temperature=0.0,
    )


@pytest.fixture
def sample_evidence() -> list[RetrievalResult]:
    return [
        RetrievalResult(
            chunk_id="c1",
            document_id="d1",
            title="Du lịch Hà Nội",
            url="https://vietnam.travel/ha-noi",
            score=0.92,
            text="Hà Nội có 36 phố phường và nhiều di tích lịch sử nổi tiếng như Hồ Gươm, Văn Miếu.",
        )
    ]


def _make_mock_client(response_text: str | None = None, raise_error: Exception | None = None) -> MagicMock:
    client = MagicMock()
    if raise_error is not None:
        client.chat.completions.create.side_effect = raise_error
    else:
        choice = MagicMock()
        choice.message.content = response_text
        completion = MagicMock()
        completion.choices = [choice]
        client.chat.completions.create.return_value = completion
    return client


def test_judge_dimensions_exact_d5_keys():
    """JUDGE_DIMENSIONS must contain the exact 6 D5 dimensions in order."""
    expected = (
        "groundedness",
        "answer_relevance",
        "correctness",
        "completeness",
        "practical_usefulness",
        "clarity",
    )
    assert JUDGE_DIMENSIONS == expected


def test_judge_valid_response(judge_config, sample_evidence):
    """Valid provider response yields judge_valid=True and locally computed total/mean."""
    valid_payload = {
        "scores": {
            "groundedness": 5,
            "answer_relevance": 4,
            "correctness": 5,
            "completeness": 4,
            "practical_usefulness": 5,
            "clarity": 5,
        },
        "reasoning": "Câu trả lời chính xác, sát tài liệu và hữu ích cho du khách.",
        "claimed_total": 999,  # Should be ignored and recomputed locally
    }
    client = _make_mock_client(json.dumps(valid_payload))
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(
        question="Hà Nội có gì đặc trưng?",
        answer="Hà Nội nổi tiếng với 36 phố phường, Hồ Gươm và Văn Miếu.",
        evidence=sample_evidence,
        reference_answer="Hà Nội có phố cổ và các di tích văn hóa.",
    )

    assert isinstance(result, JudgeResult)
    assert result.judge_valid is True
    assert result.failure_label is None
    assert result.error is None
    assert result.scores is not None
    assert result.scores["groundedness"] == 5
    assert result.scores["answer_relevance"] == 4
    assert result.total_score == 28  # 5+4+5+4+5+5 = 28
    assert result.mean_score == pytest.approx(28 / 6)
    assert result.reasoning == "Câu trả lời chính xác, sát tài liệu và hữu ích cho du khách."


def test_judge_invalid_malformed_json(judge_config, sample_evidence):
    """Malformed JSON must return judge_valid=False, failure_label='judge_invalid', no scores."""
    client = _make_mock_client("This is not JSON {invalid")
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(
        question="Q",
        answer="A",
        evidence=sample_evidence,
    )

    assert result.judge_valid is False
    assert result.failure_label == "judge_invalid"
    assert result.scores is None
    assert result.total_score is None
    assert result.mean_score is None
    assert "JSON" in str(result.error) or "json" in str(result.error).lower()


def test_judge_invalid_missing_one_criterion(judge_config, sample_evidence):
    """Missing one dimension must be rejected with judge_invalid."""
    payload = {
        "scores": {
            "groundedness": 5,
            "answer_relevance": 5,
            # missing correctness!
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        },
        "reasoning": "Missing correctness",
    }
    client = _make_mock_client(json.dumps(payload))
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(question="Q", answer="A", evidence=sample_evidence)

    assert result.judge_valid is False
    assert result.failure_label == "judge_invalid"
    assert result.scores is None
    assert "correctness" in str(result.error)


def test_judge_invalid_score_zero(judge_config, sample_evidence):
    """Score 0 is below range 1..5 and must be rejected."""
    payload = {
        "scores": {
            "groundedness": 0,
            "answer_relevance": 5,
            "correctness": 5,
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        }
    }
    client = _make_mock_client(json.dumps(payload))
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(question="Q", answer="A", evidence=sample_evidence)

    assert result.judge_valid is False
    assert result.failure_label == "judge_invalid"
    assert result.scores is None
    assert "range" in str(result.error).lower() or "0" in str(result.error)


def test_judge_invalid_score_six(judge_config, sample_evidence):
    """Score 6 is above range 1..5 and must be rejected."""
    payload = {
        "scores": {
            "groundedness": 5,
            "answer_relevance": 6,
            "correctness": 5,
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        }
    }
    client = _make_mock_client(json.dumps(payload))
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(question="Q", answer="A", evidence=sample_evidence)

    assert result.judge_valid is False
    assert result.failure_label == "judge_invalid"
    assert result.scores is None
    assert "range" in str(result.error).lower() or "6" in str(result.error)


def test_judge_invalid_wrong_enum_or_type(judge_config, sample_evidence):
    """Non-integer types (string, float, bool) must be rejected."""
    # Test float score
    payload_float = {
        "scores": {
            "groundedness": 4.5,
            "answer_relevance": 5,
            "correctness": 5,
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        }
    }
    client = _make_mock_client(json.dumps(payload_float))
    adapter = JudgeAdapter(config=judge_config, client=client)
    res_float = adapter.score(question="Q", answer="A", evidence=sample_evidence)
    assert res_float.judge_valid is False
    assert res_float.failure_label == "judge_invalid"
    assert res_float.scores is None

    # Test boolean score (which in Python is a subclass of int, so must be explicitly checked)
    payload_bool = {
        "scores": {
            "groundedness": True,
            "answer_relevance": 5,
            "correctness": 5,
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        }
    }
    client_bool = _make_mock_client(json.dumps(payload_bool))
    adapter_bool = JudgeAdapter(config=judge_config, client=client_bool)
    res_bool = adapter_bool.score(question="Q", answer="A", evidence=sample_evidence)
    assert res_bool.judge_valid is False
    assert res_bool.failure_label == "judge_invalid"
    assert res_bool.scores is None

    # Test string score
    payload_str = {
        "scores": {
            "groundedness": "5",
            "answer_relevance": 5,
            "correctness": 5,
            "completeness": 5,
            "practical_usefulness": 5,
            "clarity": 5,
        }
    }
    client_str = _make_mock_client(json.dumps(payload_str))
    adapter_str = JudgeAdapter(config=judge_config, client=client_str)
    res_str = adapter_str.score(question="Q", answer="A", evidence=sample_evidence)
    assert res_str.judge_valid is False
    assert res_str.failure_label == "judge_invalid"
    assert res_str.scores is None


def test_judge_invalid_empty_content(judge_config, sample_evidence):
    """Empty or whitespace response content must be rejected."""
    client = _make_mock_client("")
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(question="Q", answer="A", evidence=sample_evidence)

    assert result.judge_valid is False
    assert result.failure_label == "judge_invalid"
    assert result.scores is None


def test_judge_invalid_provider_exception(judge_config, sample_evidence):
    """Provider API exceptions must be caught and recorded as judge_invalid."""
    client = _make_mock_client(raise_error=RuntimeError("Provider timeout / connection refused"))
    adapter = JudgeAdapter(config=judge_config, client=client)

    result = adapter.score(question="Q", answer="A", evidence=sample_evidence)

    assert result.judge_valid is False
    assert result.failure_label == "judge_invalid"
    assert result.scores is None
    assert "Provider timeout" in str(result.error)


def test_judge_prompt_is_strategy_blind(judge_config, sample_evidence):
    """The judge prompt must NOT mention baseline, candidate, or chunking strategy names."""
    client = _make_mock_client(json.dumps({
        "scores": {dim: 5 for dim in JUDGE_DIMENSIONS},
        "reasoning": "Good",
    }))
    adapter = JudgeAdapter(config=judge_config, client=client)
    adapter.score(question="Test question", answer="Test answer", evidence=sample_evidence)

    # Inspect call to completion
    call_args = client.chat.completions.create.call_args
    messages = call_args.kwargs["messages"]
    full_prompt_text = " ".join(m["content"] for m in messages)

    forbidden_terms = ["baseline", "candidate", "parent_child", "vietnam_travel_knowledge", "vietnam_travel_parent_child"]
    for term in forbidden_terms:
        assert term not in full_prompt_text.lower(), f"Prompt leaked strategy identity: {term}"
