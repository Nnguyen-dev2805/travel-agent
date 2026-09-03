"""Strict loaders and validators for governed evaluation datasets and run configs.

Validation is a hard precondition for evaluation: invalid inputs raise
explicit ``ValueError`` messages instead of producing scores, empty-success
runs, or zero-filled labels. No embedder, vector store, LLM client, or other
external service is constructed or accessed by these loaders.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Any

from backend.app.config import settings
from backend.rag.evaluation.models import (
    DatasetManifest,
    DatasetRole,
    EvaluationDataset,
    EvaluationExample,
    JudgeConfig,
    KNOWN_SLICE_IDS,
    RunConfig,
)

DATASET_MANIFEST_NAME = "manifest.json"

DATASET_EXAMPLES_NAME = "examples.jsonl"

ALLOWED_RUNTIME_ADAPTERS: frozenset[str] = frozenset(
    {"current_runtime", "structured_runtime_v1"}
)
REQUIRED_RETRIEVAL_K_VALUES: frozenset[int] = frozenset({1, 3, 5, 10, 20})
REQUIRED_PRIMARY_K = 5
REQUIRED_SCORE_SEMANTICS = "higher_is_better_similarity"
REQUIRED_DOMAIN = "rag"

# The frozen benchmark v0.1 slice contract from the approved R1/R2 spec: a
# benchmark-role dataset must govern exactly these mandatory slices.
BENCHMARK_REQUIRED_MANDATORY_SLICES: frozenset[str] = frozenset(
    {
        "single_source_factual",
        "multi_evidence_synthesis",
        "ambiguous_underspecified",
        "source_citation_sensitive",
        "long_tail_difficult",
    }
)


def _read_json(path: Path, description: str) -> Any:
    """Read a UTF-8 JSON file and raise an explicit error on any failure."""
    if not path.is_file():
        raise ValueError(f"Missing {description} file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"{description} is not valid UTF-8: {path}") from error
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid JSON in {description}: {path}") from error


def _read_jsonl(path: Path) -> list[tuple[int, Any]]:
    """Read UTF-8 JSONL rows as (line_number, parsed_value) tuples."""
    if not path.is_file():
        raise ValueError(f"Missing dataset examples file: {path}")
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(f"Dataset examples are not valid UTF-8: {path}") from error

    rows: list[tuple[int, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append((line_number, json.loads(line)))
        except json.JSONDecodeError as error:
            raise ValueError(
                f"Invalid JSON on example line {line_number}: {path}"
            ) from error
    return rows


def _require_str(value: Any, field_name: str, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"{context} field '{field_name}' must be a non-empty string."
        )
    return value


def _parse_manifest(raw: Any) -> DatasetManifest:
    """Parse and validate the manifest object."""
    if not isinstance(raw, dict):
        raise ValueError("Dataset manifest must be a JSON object.")

    role_value = _require_str(raw.get("role"), "role", "Dataset manifest")
    try:
        role = DatasetRole(role_value)
    except ValueError as error:
        allowed = ", ".join(item.value for item in DatasetRole)
        raise ValueError(
            f"Dataset manifest has invalid role '{role_value}'. "
            f"Allowed roles: {allowed}."
        ) from error

    domain = _require_str(raw.get("domain"), "domain", "Dataset manifest")
    if domain != REQUIRED_DOMAIN:
        raise ValueError(
            f"Dataset manifest domain must be exactly '{REQUIRED_DOMAIN}'; "
            f"got '{domain}'."
        )

    if "mandatory_slices" not in raw:
        raise ValueError(
            "Dataset manifest is missing required field 'mandatory_slices'."
        )
    mandatory_slices_raw = raw["mandatory_slices"]
    if not isinstance(mandatory_slices_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in mandatory_slices_raw
    ):
        raise ValueError(
            "Dataset manifest 'mandatory_slices' must be a list of non-empty strings."
        )
    mandatory_slices = tuple(mandatory_slices_raw)
    if role is DatasetRole.BENCHMARK:
        if not mandatory_slices:
            raise ValueError(
                "Benchmark dataset manifest 'mandatory_slices' must not be empty; "
                "benchmark v0.1 must govern all frozen D5 mandatory slices."
            )
        missing_slices = sorted(
            BENCHMARK_REQUIRED_MANDATORY_SLICES - set(mandatory_slices)
        )
        if missing_slices:
            raise ValueError(
                "Benchmark dataset manifest must govern all frozen v0.1 mandatory "
                f"slices; missing {missing_slices}."
            )

    if "min_examples_per_slice" not in raw:
        raise ValueError(
            "Dataset manifest is missing required field 'min_examples_per_slice'."
        )
    min_examples_raw = raw["min_examples_per_slice"]
    if not isinstance(min_examples_raw, int) or isinstance(min_examples_raw, bool):
        raise ValueError("Dataset manifest 'min_examples_per_slice' must be an integer.")
    if min_examples_raw < 1:
        raise ValueError("Dataset manifest 'min_examples_per_slice' must be at least 1.")

    return DatasetManifest(
        dataset_id=_require_str(raw.get("dataset_id"), "dataset_id", "Dataset manifest"),
        version=_require_str(raw.get("version"), "version", "Dataset manifest"),
        role=role,
        domain=domain,
        created_at=_require_str(raw.get("created_at"), "created_at", "Dataset manifest"),
        reviewed_at=_require_str(raw.get("reviewed_at"), "reviewed_at", "Dataset manifest"),
        reviewer=_require_str(raw.get("reviewer"), "reviewer", "Dataset manifest"),
        provenance=_require_str(raw.get("provenance"), "provenance", "Dataset manifest"),
        intended_population=_require_str(
            raw.get("intended_population"), "intended_population", "Dataset manifest"
        ),
        inclusion_exclusion_rules=_require_str(
            raw.get("inclusion_exclusion_rules"),
            "inclusion_exclusion_rules",
            "Dataset manifest",
        ),
        relevance_contract=_require_str(
            raw.get("relevance_contract"), "relevance_contract", "Dataset manifest"
        ),
        mandatory_slices=mandatory_slices,
        min_examples_per_slice=min_examples_raw,
    )


def _parse_example(raw: Any, line_number: int) -> EvaluationExample:
    """Parse and validate one example row; missing relevance labels are errors."""
    context = f"Example line {line_number}"
    if not isinstance(raw, dict):
        raise ValueError(f"{context} must be a JSON object.")

    example_id = _require_str(raw.get("example_id"), "example_id", context)
    question = _require_str(raw.get("question"), "question", context)

    role_value = raw.get("dataset_role")
    if not isinstance(role_value, str) or not role_value.strip():
        raise ValueError(f"{context} '{example_id}' is missing 'dataset_role'.")
    try:
        dataset_role = DatasetRole(role_value)
    except ValueError as error:
        raise ValueError(
            f"{context} '{example_id}' has invalid dataset_role '{role_value}'."
        ) from error

    # Governed relevance labels: absence is invalid; it is never converted
    # into a valid empty example.
    if "expected_document_ids" not in raw:
        raise ValueError(
            f"{context} '{example_id}' is missing the relevance label "
            "'expected_document_ids'."
        )
    expected_document_ids_raw = raw["expected_document_ids"]
    if not isinstance(expected_document_ids_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in expected_document_ids_raw
    ):
        raise ValueError(
            f"{context} '{example_id}' field 'expected_document_ids' must be a "
            "non-empty list of non-empty strings."
        )
    if "expected_source_urls" not in raw:
        raise ValueError(
            f"{context} '{example_id}' is missing the relevance label "
            "'expected_source_urls'."
        )
    expected_source_urls_raw = raw["expected_source_urls"]
    if not isinstance(expected_source_urls_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in expected_source_urls_raw
    ):
        raise ValueError(
            f"{context} '{example_id}' field 'expected_source_urls' must be a "
            "list of non-empty strings."
        )
    if not expected_document_ids_raw:
        raise ValueError(
            f"{context} '{example_id}' has empty 'expected_document_ids'; "
            "retrieval-eligible examples require at least one expected document."
        )

    reference_answer = raw.get("reference_answer")
    if reference_answer is not None and not isinstance(reference_answer, str):
        raise ValueError(
            f"{context} '{example_id}' field 'reference_answer' must be a string or null."
        )

    slices_raw = raw.get("slices", [])
    if not isinstance(slices_raw, list) or not all(
        isinstance(item, str) and item.strip() for item in slices_raw
    ):
        raise ValueError(
            f"{context} '{example_id}' field 'slices' must be a list of strings."
        )
    for slice_id in slices_raw:
        if slice_id not in KNOWN_SLICE_IDS:
            raise ValueError(
                f"{context} '{example_id}' references unknown slice '{slice_id}'. "
                f"Known slice IDs: {', '.join(sorted(KNOWN_SLICE_IDS))}."
            )

    category = raw.get("category")
    if category is not None:
        if not isinstance(category, str) or not category.strip():
            raise ValueError(
                f"{context} '{example_id}' field 'category' must be a non-empty "
                "string when present; whitespace-only is not a reviewable "
                "classification."
            )
    if category is None and not slices_raw:
        raise ValueError(
            f"{context} '{example_id}' must declare at least one reviewable "
            "classification: 'category' or 'slices'."
        )

    return EvaluationExample(
        example_id=example_id,
        question=question,
        dataset_role=dataset_role,
        expected_document_ids=tuple(expected_document_ids_raw),
        expected_source_urls=tuple(expected_source_urls_raw),
        reference_answer=reference_answer,
        category=category,
        slices=tuple(slices_raw),
    )


def load_dataset(path: Path) -> EvaluationDataset:
    """Load and validate a manifest plus JSONL examples from ``path``.

    Raises:
        ValueError: On any manifest, encoding, schema, identity, role, slice,
            relevance-label, or coverage violation.
    """
    path = Path(path)
    manifest_raw = _read_json(path / DATASET_MANIFEST_NAME, "dataset manifest")
    manifest = _parse_manifest(manifest_raw)

    example_rows = _read_jsonl(path / DATASET_EXAMPLES_NAME)
    if not example_rows:
        raise ValueError("Dataset contains no examples; an empty dataset is not valid.")

    examples: list[EvaluationExample] = []
    seen_ids: set[str] = set()
    for line_number, raw in example_rows:
        example = _parse_example(raw, line_number)
        if example.dataset_role is not manifest.role:
            raise ValueError(
                f"Example '{example.example_id}' has dataset_role "
                f"'{example.dataset_role.value}' which disagrees with manifest role "
                f"'{manifest.role.value}'."
            )
        if example.example_id in seen_ids:
            raise ValueError(
                f"Duplicate example_id '{example.example_id}' in dataset examples."
            )
        seen_ids.add(example.example_id)
        examples.append(example)

    # Mandatory-slice coverage: every mandatory slice needs at least
    # min_examples_per_slice eligible examples.
    for mandatory_slice in manifest.mandatory_slices:
        if mandatory_slice not in KNOWN_SLICE_IDS:
            raise ValueError(
                f"Dataset manifest declares unknown mandatory slice "
                f"'{mandatory_slice}'."
            )
        covered = sum(1 for example in examples if mandatory_slice in example.slices)
        if covered == 0:
            raise ValueError(
                f"Mandatory slice '{mandatory_slice}' has no examples in dataset "
                f"'{manifest.dataset_id}' v{manifest.version}."
            )
        if covered < manifest.min_examples_per_slice:
            raise ValueError(
                f"Mandatory slice '{mandatory_slice}' has {covered} examples, below "
                f"min_examples_per_slice={manifest.min_examples_per_slice} for dataset "
                f"'{manifest.dataset_id}' v{manifest.version}."
            )

    return EvaluationDataset(manifest=manifest, examples=tuple(examples))


def _parse_judge_config(raw: Any) -> JudgeConfig:
    """Parse and validate the judge configuration object."""
    if not isinstance(raw, dict):
        raise ValueError("Run config 'judge' must be a JSON object when present.")
    temperature = raw.get("temperature")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise ValueError("Run config judge field 'temperature' must be a number.")
    schema_version = raw.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        raise ValueError("Run config judge field 'schema_version' must be an integer.")
    return JudgeConfig(
        model=_require_str(raw.get("model"), "model", "Judge config"),
        prompt_id=_require_str(raw.get("prompt_id"), "prompt_id", "Judge config"),
        rubric_id=_require_str(raw.get("rubric_id"), "rubric_id", "Judge config"),
        schema_version=schema_version,
        temperature=float(temperature),
    )


_PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z0-9_]+)\}")


def _resolve_placeholders(val: Any) -> Any:
    """Recursively resolve ${VAR} placeholders from settings and environment."""
    if isinstance(val, str):
        matches = _PLACEHOLDER_PATTERN.findall(val)
        if not matches:
            return val
        result = val
        for var_name in matches:
            resolved_val = os.getenv(var_name)
            if not resolved_val and hasattr(settings, var_name):
                resolved_val = getattr(settings, var_name)
            if not resolved_val:
                raise ValueError(
                    f"Unresolved placeholder '${{{var_name}}}' in run config: "
                    f"environment variable or setting '{var_name}' is not set."
                )
            result = result.replace(f"${{{var_name}}}", str(resolved_val))

        return result
    elif isinstance(val, dict):
        return {k: _resolve_placeholders(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_resolve_placeholders(v) for v in val]
    return val


def _parse_run_config(raw: Any) -> RunConfig:
    """Parse and validate the run-config object before anything external runs."""
    if not isinstance(raw, dict):
        raise ValueError("Run config must be a JSON object.")

    raw = _resolve_placeholders(raw)


    runtime_adapter = _require_str(
        raw.get("runtime_adapter"), "runtime_adapter", "Run config"
    )
    if runtime_adapter not in ALLOWED_RUNTIME_ADAPTERS:
        raise ValueError(
            f"Run config has invalid runtime_adapter '{runtime_adapter}'. "
            f"Allowed v0.1 adapters: {', '.join(sorted(ALLOWED_RUNTIME_ADAPTERS))}."
        )

    retrieval_k_values_raw = raw.get("retrieval_k_values")
    if not isinstance(retrieval_k_values_raw, list) or not all(
        isinstance(item, int) and not isinstance(item, bool) for item in retrieval_k_values_raw
    ):
        raise ValueError("Run config 'retrieval_k_values' must be a list of integers.")
    retrieval_k_values = tuple(retrieval_k_values_raw)
    missing_k = sorted(REQUIRED_RETRIEVAL_K_VALUES - set(retrieval_k_values))
    if missing_k:
        raise ValueError(
            f"Run config 'retrieval_k_values' must contain K values "
            f"{sorted(REQUIRED_RETRIEVAL_K_VALUES)}; missing {missing_k}."
        )

    primary_k = raw.get("primary_k")
    if not isinstance(primary_k, int) or isinstance(primary_k, bool):
        raise ValueError("Run config 'primary_k' must be an integer.")
    if primary_k != REQUIRED_PRIMARY_K:
        raise ValueError(
            f"Run config 'primary_k' must be {REQUIRED_PRIMARY_K} in v0.1; got {primary_k}."
        )

    score_semantics = _require_str(
        raw.get("score_semantics"), "score_semantics", "Run config"
    )
    if score_semantics != REQUIRED_SCORE_SEMANTICS:
        raise ValueError(
            f"Run config 'score_semantics' must be '{REQUIRED_SCORE_SEMANTICS}' for "
            f"the current Chroma adapter; got '{score_semantics}'."
        )

    generation_context_top_k = raw.get("generation_context_top_k")
    if not isinstance(generation_context_top_k, int) or isinstance(
        generation_context_top_k, bool
    ):
        raise ValueError("Run config 'generation_context_top_k' must be an integer.")

    temperature = raw.get("temperature")
    if not isinstance(temperature, (int, float)) or isinstance(temperature, bool):
        raise ValueError("Run config 'temperature' must be a number.")

    max_tokens = raw.get("max_tokens")
    if not isinstance(max_tokens, int) or isinstance(max_tokens, bool):
        raise ValueError("Run config 'max_tokens' must be an integer.")

    judge_raw = raw.get("judge")
    judge: JudgeConfig | None = None
    if judge_raw is not None:
        judge = _parse_judge_config(judge_raw)

    return RunConfig(
        config_id=_require_str(raw.get("config_id"), "config_id", "Run config"),
        version=_require_str(raw.get("version"), "version", "Run config"),
        runtime_adapter=runtime_adapter,
        collection_name=_require_str(
            raw.get("collection_name"), "collection_name", "Run config"
        ),
        embedding_model=_require_str(
            raw.get("embedding_model"), "embedding_model", "Run config"
        ),
        retrieval_k_values=retrieval_k_values,
        primary_k=primary_k,
        score_semantics=score_semantics,
        generation_context_top_k=generation_context_top_k,
        generation_model=_require_str(
            raw.get("generation_model"), "generation_model", "Run config"
        ),
        prompt_id=_require_str(raw.get("prompt_id"), "prompt_id", "Run config"),
        temperature=float(temperature),
        max_tokens=max_tokens,
        judge=judge,
    )


def load_run_config(path: Path) -> RunConfig:
    """Load and validate a JSON run-config file.

    Validation happens here before any embedder, vector store, model client,
    or other external service is constructed by later tasks.

    Raises:
        ValueError: On any schema, enum, K-value, or score-semantics violation.
    """
    path = Path(path)
    raw = _read_json(path, "run config")
    return _parse_run_config(raw)


validate_run_config = _parse_run_config
