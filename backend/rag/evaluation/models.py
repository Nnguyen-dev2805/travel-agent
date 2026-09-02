"""Evaluation value models for the R2 harness.

Defines the strict dataset/run/judge/result-state contracts for R2 v0.1 per
the approved R1/R2 specification, ADR 0001, and the accepted D5 evaluation
protocol. These models are evaluation-owned: online RAG runtime code must not
import this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# The v0.1 benchmark slice vocabulary from the approved R1/R2 specification.
KNOWN_SLICE_IDS: frozenset[str] = frozenset(
    {
        "single_source_factual",
        "multi_evidence_synthesis",
        "ambiguous_underspecified",
        "source_citation_sensitive",
        "long_tail_difficult",
    }
)


class DatasetRole(str, Enum):
    """Role a governed dataset plays in the evaluation lifecycle."""

    DEVELOPMENT = "development"
    REGRESSION = "regression"
    BENCHMARK = "benchmark"
    SAFETY = "safety"


class ResultState(str, Enum):
    """Final governed result states allowed by the D5 protocol."""

    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    INVALID = "INVALID"


@dataclass(frozen=True)
class DatasetManifest:
    """Immutable identity and review metadata for one dataset version."""

    dataset_id: str
    version: str
    role: DatasetRole
    domain: str
    created_at: str
    reviewed_at: str
    reviewer: str
    provenance: str
    intended_population: str
    inclusion_exclusion_rules: str
    relevance_contract: str
    mandatory_slices: tuple[str, ...]
    min_examples_per_slice: int


@dataclass(frozen=True)
class EvaluationExample:
    """One evaluated query with its governed relevance labels.

    ``expected_document_ids`` is the governed document-level relevance label
    required for retrieval metrics. Missing labels must never be silently
    converted into valid empty examples.
    """

    example_id: str
    question: str
    dataset_role: DatasetRole
    expected_document_ids: tuple[str, ...]
    expected_source_urls: tuple[str, ...]
    reference_answer: str | None
    category: str | None = None
    slices: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvaluationDataset:
    """A validated manifest plus its eligible examples."""

    manifest: DatasetManifest
    examples: tuple[EvaluationExample, ...] = field(default=())


@dataclass(frozen=True)
class JudgeConfig:
    """Frozen identity of the answer-quality judge contract."""

    model: str
    prompt_id: str
    rubric_id: str
    schema_version: int
    temperature: float


@dataclass(frozen=True)
class RunConfig:
    """Frozen behavior identity for one evaluation run.

    Records what behavior executes, not an experiment role. Baseline and
    candidate labels are assigned to run artifacts at comparison time and are
    deliberately absent here (ADR 0001).
    """

    config_id: str
    version: str
    runtime_adapter: str
    collection_name: str
    embedding_model: str
    retrieval_k_values: tuple[int, ...]
    primary_k: int
    score_semantics: str
    generation_context_top_k: int
    generation_model: str
    prompt_id: str
    temperature: float
    max_tokens: int
    judge: JudgeConfig | None = None
