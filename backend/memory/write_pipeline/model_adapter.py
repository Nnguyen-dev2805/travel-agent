"""Structured model adapter for bilingual semantic memory extraction.

Handles:
- Vietnamese and English extraction and normalization for travel.preference.hotel_atmosphere
- Strict Pydantic candidate schema with extra="forbid"
- Single bounded repair on malformed/invalid model response
- Pre-model secret filtering to prevent sensitive credentials from reaching LLM providers
- Classification of transient vs permanent provider errors
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.memory.write_pipeline.models import (
    Authority,
    MemoryCandidate,
    MemoryRelation,
    MemoryScope,
    SensitivityBand,
    new_candidate_id,
)
from backend.memory.write_pipeline.registry import (
    HOTEL_ATMOSPHERE_KEY,
    RegistryValidationError,
    normalize_value,
)
from backend.memory.write_pipeline.secrets import detect_prohibited_content

logger = logging.getLogger("travel_agent_memory_model_adapter")

PROMPT_VERSION = "2026-09-07.v1"
SCHEMA_VERSION = "2026-09-07.v1"


@dataclass(frozen=True)
class TokenUsage:
    """Token usage metrics for model extraction and classification."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def __post_init__(self) -> None:
        if self.total_tokens == 0 and (self.prompt_tokens or self.completion_tokens):
            object.__setattr__(
                self, "total_tokens", self.prompt_tokens + self.completion_tokens
            )


@dataclass(frozen=True)
class CostEvidence:
    """Cost evidence tracking prompt/schema versions and estimated expense."""

    estimated_cost_usd: float = 0.0
    model_name: str = ""
    prompt_version: str = PROMPT_VERSION
    schema_version: str = SCHEMA_VERSION


class ModelAdapterError(Exception):
    """Base class for model adapter failures."""


class ProviderTransientError(ModelAdapterError):
    """Transient provider failure (e.g. rate limit 429, 503, connection timeout)."""


class ProviderPermanentError(ModelAdapterError):
    """Permanent provider failure (e.g. 400, 401, 403, or invalid schema after repair)."""


class LLMProvider(Protocol):
    """Protocol for the underlying generative model client."""

    def generate(self, prompt: str, **kwargs: Any) -> str:
        """Generate text from the configured model."""
        ...


class ExtractionCandidateSchema(BaseModel):
    """Strict schema for one extracted preference candidate."""

    model_config = ConfigDict(extra="forbid")

    canonical_key: str
    value: str
    display_text: str
    confidence: float = 1.0


class ExtractionOutputSchema(BaseModel):
    """Strict root schema for the model's extraction output."""

    model_config = ConfigDict(extra="forbid")

    candidates: list[ExtractionCandidateSchema] = Field(default_factory=list)


class RelationClassificationSchema(BaseModel):
    """Strict schema for relationship classification between a candidate and an existing memory."""

    model_config = ConfigDict(extra="forbid")

    relation: MemoryRelation
    rationale: str = ""
    confidence: float = 1.0


class StructuredRelationPrompt:
    """Prompt templates for semantic relation classification."""

    SYSTEM_INSTRUCTIONS = (
        "You are an expert travel assistant classifying the semantic relationship between a new candidate memory and an existing stored memory.\n"
        "The relationship MUST be one of the following exact closed-vocabulary options:\n"
        "- 'same': The candidate conveys the identical preference.\n"
        "- 'compatible': The candidate can coexist without conflict.\n"
        "- 'contradiction': The candidate directly conflicts with the existing preference.\n"
        "- 'temporal_update': The candidate updates an earlier preference over time.\n"
        "- 'scope_exception': The candidate is an exception for a specific trip or context.\n"
        "- 'unrelated': The preferences are about unrelated topics.\n"
        "- 'uncertain': The relationship is ambiguous or confidence is low.\n"
        "Respond ONLY with valid JSON conforming to: "
        '{"relation": "<relation>", "rationale": "<explanation>", "confidence": 1.0}\n'
    )

    @classmethod
    def build_prompt(cls, candidate: MemoryCandidate, existing: Any) -> str:
        existing_val = getattr(existing, "normalized_value", str(existing))
        existing_text = getattr(existing, "display_text", "")
        return (
            f"{cls.SYSTEM_INSTRUCTIONS}\n"
            "--- Comparison ---\n"
            f"Candidate Key: {candidate.canonical_key}\n"
            f"Candidate Value: {candidate.normalized_value} ({candidate.display_text})\n"
            f"Existing Value: {existing_val} ({existing_text})\n"
            "--- End Comparison ---\n"
            "JSON Output:"
        )

    @classmethod
    def build_repair_prompt(cls, raw_output: str, error_details: str) -> str:
        return (
            f"{cls.SYSTEM_INSTRUCTIONS}\n"
            "The previous model output failed relation schema validation:\n"
            f"Error: {error_details}\n"
            f"Previous Output: {raw_output}\n"
            "Please fix the format and output ONLY valid JSON matching the relation schema."
        )



class StructuredExtractionPrompt:
    """Prompt templates for focused preference extraction."""

    SYSTEM_INSTRUCTIONS = (
        "You are an expert travel assistant extracting user preferences from conversation messages.\n"
        "Focus ONLY on the hotel atmosphere preference key:\n"
        f"- Canonical key: '{HOTEL_ATMOSPHERE_KEY}'\n"
        "- Allowed atmosphere values: quiet, lively, central, secluded.\n"
        "Bilingual support: User may express in English or Vietnamese (e.g., 'yên tĩnh' -> quiet, 'sôi động' -> lively, 'trung tâm' -> central, 'biệt lập' -> secluded).\n"
        "Respond ONLY with valid JSON conforming to the following JSON schema:\n"
        '{"candidates": [{"canonical_key": "travel.preference.hotel_atmosphere", "value": "<value>", "display_text": "<text>", "confidence": 1.0}]}\n'
        "If no hotel atmosphere preference is mentioned, return: {\"candidates\": []}\n"
    )

    @classmethod
    def build_prompt(cls, messages: Sequence[dict[str, Any]]) -> str:
        transcript_lines = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            transcript_lines.append(f"{role}: {content}")
        transcript = "\n".join(transcript_lines)
        return (
            f"{cls.SYSTEM_INSTRUCTIONS}\n"
            "--- Conversation Transcript ---\n"
            f"{transcript}\n"
            "--- End Transcript ---\n"
            "JSON Output:"
        )

    @classmethod
    def build_repair_prompt(cls, raw_output: str, error_details: str) -> str:
        return (
            f"{cls.SYSTEM_INSTRUCTIONS}\n"
            "The previous model output failed schema validation:\n"
            f"Error: {error_details}\n"
            f"Previous Output: {raw_output}\n"
            "Please fix the format and output ONLY valid JSON matching the schema."
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MemoryExtractionModel:
    """Extracts typed memory candidates from conversation transcripts."""

    def __init__(
        self,
        provider: LLMProvider | None = None,
        model_name: str = "gemini-2.5-flash",
        max_repair_attempts: int = 1,
    ) -> None:
        self._provider = provider
        self._model_name = model_name
        self._max_repair_attempts = max_repair_attempts
        self._last_token_usage: TokenUsage | None = None
        self._last_cost_evidence: CostEvidence | None = None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def prompt_version(self) -> str:
        return PROMPT_VERSION

    @property
    def schema_version(self) -> str:
        return SCHEMA_VERSION

    @property
    def last_token_usage(self) -> TokenUsage | None:
        return self._last_token_usage

    @property
    def last_cost_evidence(self) -> CostEvidence | None:
        return self._last_cost_evidence

    def extract(
        self,
        messages: Sequence[dict[str, Any]],
        owner_user_id: str,
        conversation_id: str,
        evidence_ids: tuple[str, ...] = (),
    ) -> Sequence[MemoryCandidate]:
        """Extract memory candidates from message turns, enforcing privacy and schema rules."""
        if not messages:
            return ()

        # 1. Deterministic pre-model secret filter:
        # If any message contains a prohibited secret, reject immediately without sending to LLM.
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and detect_prohibited_content(content) is not None:
                logger.warning(
                    "Pre-model secret scan detected prohibited content; skipping model call conversation_id=%s",
                    conversation_id,
                )
                return ()

        if self._provider is None:
            return ()

        # 2. Build prompt and call provider
        prompt = StructuredExtractionPrompt.build_prompt(messages)
        try:
            raw_response = self._provider.generate(prompt)
            self._track_usage(prompt, raw_response)
        except (ProviderTransientError, ProviderPermanentError):
            raise
        except Exception as error:
            error_str = str(error).lower()
            if any(t in error_str for t in ("429", "503", "rate limit", "timeout", "temporarily unavailable")):
                raise ProviderTransientError(f"Transient model error: {error}") from error
            raise ProviderPermanentError(f"Permanent model error: {error}") from error

        # 3. Parse JSON with bounded repair
        parsed_output = self._parse_with_repair(raw_response)

        # 4. Filter, normalize, and construct MemoryCandidate domain objects
        candidates: list[MemoryCandidate] = []
        observed_time = _utc_now()

        for raw_cand in parsed_output.candidates:
            # Strictly filter to known key in focused scope
            if raw_cand.canonical_key != HOTEL_ATMOSPHERE_KEY:
                logger.debug("Skipping candidate with outside-scope key: %s", raw_cand.canonical_key)
                continue

            try:
                norm_val = normalize_value(raw_cand.canonical_key, raw_cand.value)
            except RegistryValidationError:
                logger.debug("Skipping candidate with un-normalizable value: %s", raw_cand.value)
                continue

            candidate = MemoryCandidate(
                candidate_id=new_candidate_id(),
                evidence_ids=evidence_ids,
                owner_user_id=owner_user_id,
                scope=MemoryScope.CONVERSATION,
                conversation_id=conversation_id,
                canonical_key=HOTEL_ATMOSPHERE_KEY,
                normalized_value=norm_val,
                display_text=raw_cand.display_text,
                authority=Authority.REPEATED_INFERENCE,
                sensitivity=SensitivityBand.ORDINARY_PERSONAL,
                subject_key="self",
                condition="",
                observed_at=observed_time,
            )
            candidates.append(candidate)

        return tuple(candidates)

    def _track_usage(self, prompt: str, response: str) -> None:
        p_usage = getattr(self._provider, "last_token_usage", None)
        if isinstance(p_usage, TokenUsage):
            self._last_token_usage = p_usage
        else:
            prompt_tokens = max(1, len(prompt) // 4)
            completion_tokens = max(1, len(response) // 4)
            self._last_token_usage = TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=prompt_tokens + completion_tokens,
            )
        cost = (
            (self._last_token_usage.prompt_tokens * 0.075 / 1_000_000)
            + (self._last_token_usage.completion_tokens * 0.30 / 1_000_000)
        )
        self._last_cost_evidence = CostEvidence(
            estimated_cost_usd=round(cost, 8),
            model_name=self._model_name,
            prompt_version=self.prompt_version,
            schema_version=self.schema_version,
        )

    def _parse_with_repair(self, raw_response: str) -> ExtractionOutputSchema:
        """Parse the raw response into ExtractionOutputSchema, attempting bounded repair if invalid."""
        try:
            data = json.loads(raw_response)
            return ExtractionOutputSchema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as initial_error:
            logger.info("Model response invalid; attempting bounded repair. Error: %s", initial_error)
            if self._max_repair_attempts <= 0:
                raise ProviderPermanentError(f"Schema validation failed: {initial_error}") from initial_error

            # 1 repair attempt
            repair_prompt = StructuredExtractionPrompt.build_repair_prompt(
                raw_response, str(initial_error)
            )
            try:
                repaired_response = self._provider.generate(repair_prompt)
                self._track_usage(repair_prompt, repaired_response)
                repaired_data = json.loads(repaired_response)
                return ExtractionOutputSchema.model_validate(repaired_data)
            except (ProviderTransientError, ProviderPermanentError):
                raise
            except Exception as repair_error:
                raise ProviderPermanentError(
                    f"Model response failed schema validation after repair attempt: {repair_error}"
                ) from repair_error

    def classify_relation(
        self,
        candidate: MemoryCandidate,
        existing: Any,
    ) -> MemoryRelation:
        """Classify semantic relationship between a candidate and existing memory with bounded repair and fallback."""
        existing_key = getattr(existing, "canonical_key", candidate.canonical_key)
        if candidate.canonical_key != existing_key:
            return MemoryRelation.UNRELATED

        existing_val = getattr(existing, "normalized_value", None)
        if existing_val is not None and candidate.normalized_value == existing_val:
            return MemoryRelation.SAME

        if self._provider is None:
            return MemoryRelation.UNCERTAIN

        prompt = StructuredRelationPrompt.build_prompt(candidate, existing)
        try:
            raw_response = self._provider.generate(prompt)
            self._track_usage(prompt, raw_response)
        except (ProviderTransientError, ProviderPermanentError):
            raise
        except Exception as error:
            error_str = str(error).lower()
            if any(t in error_str for t in ("429", "503", "rate limit", "timeout", "temporarily unavailable")):
                raise ProviderTransientError(f"Transient model error in relation classification: {error}") from error
            logger.warning("Provider error in relation classification; falling back to UNCERTAIN: %s", error)
            return MemoryRelation.UNCERTAIN

        return self._parse_relation_with_repair(raw_response)

    def _parse_relation_with_repair(self, raw_response: str) -> MemoryRelation:
        """Parse relation schema with 1 bounded repair and fallback to UNCERTAIN."""
        try:
            data = json.loads(raw_response)
            parsed = RelationClassificationSchema.model_validate(data)
            return parsed.relation
        except (json.JSONDecodeError, ValidationError) as initial_error:
            logger.info("Relation output invalid; attempting bounded repair. Error: %s", initial_error)
            if self._max_repair_attempts <= 0:
                logger.warning("Max repair attempts reached for relation; falling back to UNCERTAIN")
                return MemoryRelation.UNCERTAIN

            repair_prompt = StructuredRelationPrompt.build_repair_prompt(
                raw_response, str(initial_error)
            )
            try:
                repaired_response = self._provider.generate(repair_prompt)
                self._track_usage(repair_prompt, repaired_response)
                repaired_data = json.loads(repaired_response)
                parsed = RelationClassificationSchema.model_validate(repaired_data)
                return parsed.relation
            except Exception as repair_error:
                logger.warning(
                    "Relation repair failed; falling back to UNCERTAIN: %s",
                    repair_error,
                )
                return MemoryRelation.UNCERTAIN

