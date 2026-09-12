"""Unit tests for the structured model adapter for memory candidate extraction.

Covers:
- Vietnamese and English extraction and normalization for travel.preference.hotel_atmosphere
- Strict Pydantic candidate schema with extra="forbid"
- Single bounded repair on malformed/invalid model response
- Bounded repair exhaustion fails closed
- ProviderTransientError on 429/503/timeout
- ProviderPermanentError on auth/malformed irrecoverable errors
- Pre-model secret scan prevents leak to provider
"""

from datetime import datetime, timezone
import pytest

from backend.memory.write_pipeline.models import (
    Authority,
    MemoryCandidate,
    MemoryRelation,
    MemoryScope,
    SensitivityBand,
    new_candidate_id,
)
from backend.memory.write_pipeline.registry import HOTEL_ATMOSPHERE_KEY
from backend.memory.write_pipeline.model_adapter import (
    CostEvidence,
    MemoryExtractionModel,
    ModelAdapterError,
    PROMPT_VERSION,
    ProviderPermanentError,
    ProviderTransientError,
    SCHEMA_VERSION,
    StructuredExtractionPrompt,
    TokenUsage,
    schema_failure_reason,
)


class MockLLMProvider:
    """Mock LLM provider for simulating structured outputs, repair, and errors."""

    def __init__(self, responses=None):
        # responses can be a list of strings or Exceptions
        self.responses = list(responses or [])
        self.call_count = 0
        self.prompts_received = []

    def generate(self, prompt: str, **kwargs) -> str:
        self.call_count += 1
        self.prompts_received.append(prompt)
        if not self.responses:
            return '{"candidates": []}'
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        return resp


def test_extract_english_candidate():
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "quiet", "display_text": "I like quiet hotels"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    candidates = model.extract(
        messages=[{"role": "user", "content": "I like quiet hotels"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.canonical_key == HOTEL_ATMOSPHERE_KEY
    assert cand.normalized_value == "quiet"
    assert cand.display_text == "I like quiet hotels"
    assert cand.authority == Authority.REPEATED_INFERENCE
    assert cand.scope == MemoryScope.CONVERSATION
    assert cand.sensitivity == SensitivityBand.ORDINARY_PERSONAL


def test_extract_vietnamese_candidate():
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "yên tĩnh", "display_text": "thích khách sạn yên tĩnh"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    candidates = model.extract(
        messages=[{"role": "user", "content": "Tôi thích khách sạn yên tĩnh"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.canonical_key == HOTEL_ATMOSPHERE_KEY
    assert cand.normalized_value == "quiet"  # Normalized from Vietnamese "yên tĩnh"
    assert cand.display_text == "thích khách sạn yên tĩnh"


def test_repair_succeeds_on_malformed_json_first_attempt():
    provider = MockLLMProvider(
        [
            "MALFORMED_JSON{not valid}",  # 1st attempt
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "secluded", "display_text": "secluded stay"}]}',  # 2nd attempt (repaired)
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    candidates = model.extract(
        messages=[{"role": "user", "content": "Prefer secluded vibe"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert len(candidates) == 1
    assert candidates[0].normalized_value == "secluded"
    assert provider.call_count == 2
    assert (
        "repair" in provider.prompts_received[1].lower()
        or "fix" in provider.prompts_received[1].lower()
    )


def test_repair_exhaustion_fails_closed():
    provider = MockLLMProvider(
        [
            "MALFORMED_JSON{1}",  # 1st attempt
            "STILL_MALFORMED{2}",  # 2nd attempt (repair fails)
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    with pytest.raises(ProviderPermanentError) as exc_info:
        model.extract(
            messages=[{"role": "user", "content": "Something"}],
            owner_user_id="user_1",
            conversation_id="conv_1",
        )
    assert (
        "schema" in str(exc_info.value).lower()
        or "repair" in str(exc_info.value).lower()
    )
    assert provider.call_count == 2


def test_transient_error_propagates():
    provider = MockLLMProvider([ProviderTransientError("Rate limit 429")])
    model = MemoryExtractionModel(provider=provider)
    with pytest.raises(ProviderTransientError):
        model.extract(
            messages=[{"role": "user", "content": "Hello"}],
            owner_user_id="user_1",
            conversation_id="conv_1",
        )


def test_pre_model_secret_detection_prevents_provider_call():
    provider = MockLLMProvider()
    model = MemoryExtractionModel(provider=provider)
    candidates = model.extract(
        messages=[
            {"role": "user", "content": "My secret key is sk-proj-1234567890abcdef"}
        ],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )
    # No candidate should be produced, and provider must NOT be called
    assert len(candidates) == 0
    assert provider.call_count == 0


def test_post_extraction_secret_in_model_output_is_dropped():
    """A model echo of prohibited material must not become a candidate."""
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "quiet", "display_text": "token: sk-proj-1234567890abcdef"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    candidates = model.extract(
        messages=[{"role": "user", "content": "I like quiet hotels"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )
    assert candidates == ()


def test_unknown_key_filtered_out():
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.flight.seat", "value": "window", "display_text": "window seat"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    candidates = model.extract(
        messages=[{"role": "user", "content": "I want a window seat"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )
    # Outside focused scope key -> filtered out
    assert len(candidates) == 0


def test_classify_relation_same_and_unrelated_fast_path():
    provider = MockLLMProvider()
    model = MemoryExtractionModel(provider=provider)

    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="u1",
        scope=MemoryScope.USER,
        conversation_id=None,
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="quiet",
        display_text="quiet hotel",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )

    class Existing:
        canonical_key = HOTEL_ATMOSPHERE_KEY
        normalized_value = "quiet"
        display_text = "I like quiet places"

    # Exact value match -> SAME (no LLM call)
    assert model.classify_relation(candidate, Existing()) == MemoryRelation.SAME
    assert provider.call_count == 0

    class Unrelated:
        canonical_key = "travel.flight.airline"
        normalized_value = "vn_airlines"

    # Different key -> UNRELATED (no LLM call)
    assert model.classify_relation(candidate, Unrelated()) == MemoryRelation.UNRELATED
    assert provider.call_count == 0


def test_classify_relation_model_contradiction():
    provider = MockLLMProvider(
        [
            '{"relation": "contradiction", "rationale": "Quiet conflicts with lively", "confidence": 0.95}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="u1",
        scope=MemoryScope.USER,
        conversation_id=None,
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="lively",
        display_text="lively vibe",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )

    class Existing:
        canonical_key = HOTEL_ATMOSPHERE_KEY
        normalized_value = "quiet"
        display_text = "quiet places"

    relation = model.classify_relation(candidate, Existing())
    assert relation == MemoryRelation.CONTRADICTION
    assert provider.call_count == 1


def test_classify_relation_repair_succeeds():
    provider = MockLLMProvider(
        [
            "INVALID_OUTPUT_NO_JSON",  # 1st attempt
            '{"relation": "temporal_update", "rationale": "Switched from central to quiet", "confidence": 0.9}',  # 2nd attempt
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="u1",
        scope=MemoryScope.USER,
        conversation_id=None,
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="quiet",
        display_text="quiet hotel",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )

    class Existing:
        canonical_key = HOTEL_ATMOSPHERE_KEY
        normalized_value = "central"
        display_text = "central places"

    relation = model.classify_relation(candidate, Existing())
    assert relation == MemoryRelation.TEMPORAL_UPDATE
    assert provider.call_count == 2


def test_classify_relation_fallback_to_uncertain_when_repair_exhausted():
    provider = MockLLMProvider(
        [
            "INVALID_JSON_1",  # 1st attempt
            "STILL_INVALID_JSON_2",  # 2nd attempt
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    candidate = MemoryCandidate(
        candidate_id=new_candidate_id(),
        evidence_ids=(),
        owner_user_id="u1",
        scope=MemoryScope.USER,
        conversation_id=None,
        canonical_key=HOTEL_ATMOSPHERE_KEY,
        normalized_value="secluded",
        display_text="secluded hotel",
        authority=Authority.REPEATED_INFERENCE,
        sensitivity=SensitivityBand.ORDINARY_PERSONAL,
        observed_at=datetime.now(timezone.utc),
    )

    class Existing:
        canonical_key = HOTEL_ATMOSPHERE_KEY
        normalized_value = "central"
        display_text = "central places"

    # Fails closed to UNCERTAIN without raising unhandled error
    relation = model.classify_relation(candidate, Existing())
    assert relation == MemoryRelation.UNCERTAIN
    assert provider.call_count == 2


def test_token_usage_and_cost_evidence():
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "quiet", "display_text": "I like quiet hotels"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)
    assert model.prompt_version == PROMPT_VERSION
    assert model.schema_version == SCHEMA_VERSION
    assert model.last_token_usage is None
    assert model.last_cost_evidence is None

    model.extract(
        messages=[{"role": "user", "content": "I like quiet hotels"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert model.last_token_usage is not None
    assert model.last_token_usage.total_tokens > 0
    assert model.last_token_usage.prompt_tokens > 0
    assert model.last_token_usage.completion_tokens > 0

    assert model.last_cost_evidence is not None
    assert model.last_cost_evidence.estimated_cost_usd > 0
    assert model.last_cost_evidence.model_name == "gemini-2.5-flash"
    assert model.last_cost_evidence.prompt_version == PROMPT_VERSION
    assert model.last_cost_evidence.schema_version == SCHEMA_VERSION


# --- C5: extracted user content must not reach a log or a persisted error ---

USER_CONTENT = "Hà Nội có quán cà phê yên tĩnh"


def _validation_error_carrying(content: str):
    """Build a real pydantic ValidationError whose rendering embeds `content`."""
    from pydantic import ValidationError

    from backend.memory.write_pipeline.model_adapter import ExtractionOutputSchema

    with pytest.raises(ValidationError) as excinfo:
        ExtractionOutputSchema.model_validate(
            {"candidates": [{"canonical_key": 1, "value": content}]}
        )
    return excinfo.value


def test_schema_failure_reason_reports_field_paths_not_values():
    reason = schema_failure_reason(_validation_error_carrying(USER_CONTENT))

    assert reason.startswith("schema_validation_failed")
    assert "candidates" in reason
    assert USER_CONTENT not in reason


def test_schema_failure_reason_never_renders_an_arbitrary_exception():
    reason = schema_failure_reason(RuntimeError(USER_CONTENT))

    assert reason == "model_adapter_failed class=RuntimeError"
    assert USER_CONTENT not in reason


def test_validation_failure_log_carries_no_extracted_content(caplog):
    adapter = MemoryExtractionModel(provider=MockLLMProvider(), max_repair_attempts=0)

    with caplog.at_level("INFO"):
        with pytest.raises(ProviderPermanentError):
            adapter._parse_with_repair('{"candidates": [{"canonical_key": 1, "value": "%s"}]}' % USER_CONTENT)

    assert USER_CONTENT not in caplog.text
    assert "input_value" not in caplog.text
    assert "schema_validation_failed" in caplog.text


def test_permanent_error_message_carries_no_extracted_content():
    with pytest.raises(ProviderPermanentError) as excinfo:
        MemoryExtractionModel(
            provider=MockLLMProvider(), max_repair_attempts=0
        )._parse_with_repair(
            '{"candidates": [{"canonical_key": 1, "value": "%s"}]}' % USER_CONTENT
        )

    assert USER_CONTENT not in str(excinfo.value)
    assert "input_value" not in str(excinfo.value)


# --- C9: the model's confidence must reach the candidate --------------------


def test_extract_carries_the_model_confidence_onto_the_candidate():
    """C9: the adapter must not drop the model's confidence on the floor.

    `MemoryCandidate` did not declare the field, so `_to_memory_candidate`
    dropped it and the recorder's gate always saw `1.0`. The threshold was
    therefore never applied to the only producer of candidates.
    """
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", '
            '"value": "quiet", "display_text": "I like quiet hotels", '
            '"confidence": 0.3}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    candidates = model.extract(
        messages=[{"role": "user", "content": "I like quiet hotels"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert len(candidates) == 1
    assert candidates[0].confidence == pytest.approx(0.3)


def test_extract_defaults_confidence_when_the_model_omits_it():
    """The default is declared in the schema, not an accident of a missing field."""
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", '
            '"value": "quiet", "display_text": "I like quiet hotels"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    candidates = model.extract(
        messages=[{"role": "user", "content": "I like quiet hotels"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert candidates[0].confidence == pytest.approx(1.0)


def test_extract_confidence_of_zero_survives_to_the_candidate():
    """A model that scores its own output `0.0` must not be rounded up."""
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", '
            '"value": "quiet", "display_text": "I like quiet hotels", '
            '"confidence": 0.0}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    candidates = model.extract(
        messages=[{"role": "user", "content": "I like quiet hotels"}],
        owner_user_id="user_1",
        conversation_id="conv_1",
    )

    assert candidates[0].confidence == pytest.approx(0.0)


# --- C5 extended: the two candidate-rejection paths logged model output --------

REJECTED_VALUE_SENTINEL = "SENTINEL-USER-VALUE-9f3c"
REJECTED_KEY_SENTINEL = "SENTINEL-MODEL-KEY-7b21"


def test_a_rejected_candidate_logs_no_model_output(caplog):
    """Both rejection paths used to log a value straight from the model's JSON.

    `raw_cand.value` and `raw_cand.canonical_key` arrive in the model's output, and
    the prompt is built from conversation messages — so either can carry user
    content. SECURITY.md: full prompt, conversation, retrieved content or
    model-output logging is not the default mechanism. The rejections now log a
    governed code, which is the same rule `schema_failure_reason` already
    documents for the other four log sites in this module.

    Both paths are exercised in one call, because the defect was two lines and a
    test that covered one would have passed with the other still leaking.
    """
    provider = MockLLMProvider(
        [
            '{"candidates": ['
            # Rejected for its key, which is model-chosen and untrusted.
            '{"canonical_key": "SENTINEL-MODEL-KEY-7b21", '
            '"value": "SENTINEL-USER-VALUE-9f3c", "display_text": "x"}, '
            # Correct key, but a value the registry cannot normalize.
            '{"canonical_key": "travel.preference.hotel_atmosphere", '
            '"value": "SENTINEL-USER-VALUE-9f3c", "display_text": "x"}'
            "]}"
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    with caplog.at_level("DEBUG"):
        candidates = model.extract(
            messages=[{"role": "user", "content": REJECTED_VALUE_SENTINEL}],
            owner_user_id="user_1",
            conversation_id="conv_1",
        )

    assert candidates == (), "both candidates must be rejected"
    assert REJECTED_VALUE_SENTINEL not in caplog.text, (
        "model output must not reach the log stream"
    )
    assert REJECTED_KEY_SENTINEL not in caplog.text, (
        "a model-chosen key is untrusted content, not registry metadata"
    )
    # The rejections stay observable: a governed code, not silence.
    assert "outside_scope_key" in caplog.text
    assert "un_normalizable_value" in caplog.text


def test_a_rejected_candidate_still_names_the_registry_key(caplog):
    """The un-normalizable path may name the key, because it is the constant.

    Distinguishing this from the previous test is the point: `key=` is safe only
    after the key has been proved equal to `HOTEL_ATMOSPHERE_KEY`.
    """
    provider = MockLLMProvider(
        [
            '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", '
            '"value": "not-in-the-vocabulary", "display_text": "x"}]}'
        ]
    )
    model = MemoryExtractionModel(provider=provider)

    with caplog.at_level("DEBUG"):
        model.extract(
            messages=[{"role": "user", "content": "anything"}],
            owner_user_id="user_1",
            conversation_id="conv_1",
        )

    assert f"key={HOTEL_ATMOSPHERE_KEY}" in caplog.text
