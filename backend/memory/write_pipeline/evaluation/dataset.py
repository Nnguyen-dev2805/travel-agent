"""Dataset loading, validation, and parsing for the memory write pipeline evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.memory.write_pipeline.evaluation.models import (
    DatasetManifest,
    EvaluationExample,
    MANDATORY_SLICES,
)


class DatasetError(Exception):
    """Base exception for evaluation dataset errors."""


class DatasetValidationError(DatasetError):
    """The dataset manifest or examples violate the evaluation contract."""


def load_dataset(
    dataset_path: str | Path,
) -> tuple[DatasetManifest, tuple[EvaluationExample, ...]]:
    """Load and validate dataset manifest and examples from directory or manifest file."""
    path = Path(dataset_path)
    if path.is_dir():
        manifest_file = path / "manifest.json"
        examples_file = path / "examples.jsonl"
    else:
        manifest_file = path
        examples_file = path.parent / "examples.jsonl"

    if not manifest_file.exists():
        raise DatasetValidationError(f"Manifest file not found: {manifest_file}")
    if not examples_file.exists():
        raise DatasetValidationError(f"Examples file not found: {examples_file}")

    try:
        manifest_data = json.loads(manifest_file.read_text(encoding="utf-8"))
    except Exception as err:
        raise DatasetValidationError(f"Malformed manifest JSON: {err}") from err

    required_manifest_keys = {
        "dataset_id",
        "role",
        "languages",
        "canonical_key",
        "values",
        "version",
        "examples_count",
    }
    missing = required_manifest_keys - set(manifest_data.keys())
    if missing:
        raise DatasetValidationError(f"Manifest missing required keys: {sorted(missing)}")

    manifest = DatasetManifest(
        dataset_id=manifest_data["dataset_id"],
        role=manifest_data["role"],
        languages=tuple(manifest_data["languages"]),
        canonical_key=manifest_data["canonical_key"],
        values=tuple(manifest_data["values"]),
        version=manifest_data["version"],
        examples_count=int(manifest_data["examples_count"]),
        mandatory_slices=tuple(manifest_data.get("mandatory_slices", MANDATORY_SLICES)),
    )

    examples: list[EvaluationExample] = []
    seen_ids: set[str] = set()
    slices_present: set[str] = set()

    line_number = 0
    with examples_file.open("r", encoding="utf-8") as f:
        for line in f:
            line_number += 1
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                data = json.loads(line)
            except Exception as err:
                raise DatasetValidationError(
                    f"Malformed JSON on line {line_number} of {examples_file}: {err}"
                ) from err

            if "example_id" not in data or not data["example_id"]:
                raise DatasetValidationError(f"Missing example_id on line {line_number}")
            eid = data["example_id"]
            if eid in seen_ids:
                raise DatasetValidationError(f"Duplicate example_id: '{eid}'")
            seen_ids.add(eid)

            slice_name = data.get("slice", "")
            if not slice_name:
                raise DatasetValidationError(f"Missing slice for example '{eid}'")
            slices_present.add(slice_name)

            example = EvaluationExample(
                example_id=eid,
                slice=slice_name,
                language=data.get("language", "en"),
                source_events=tuple(data.get("source_events", ())),
                existing_assertions_and_versions=tuple(
                    data.get("existing_assertions_and_versions", ())
                ),
                expected_candidates=tuple(data.get("expected_candidates", ())),
                expected_decisions=tuple(data.get("expected_decisions", ())),
                expected_change_set=data.get("expected_change_set"),
                expected_persisted_state=data.get("expected_persisted_state"),
                expected_outbox_state=data.get("expected_outbox_state"),
                expected_trace_fields=data.get("expected_trace_fields"),
                expected_user_response_contract=data.get("expected_user_response_contract"),
                hard_gate=data.get("hard_gate"),
            )
            examples.append(example)

    # Invariant: Empty mandatory slice makes the dataset invalid
    missing_mandatory = set(manifest.mandatory_slices) - slices_present
    if missing_mandatory:
        raise DatasetValidationError(
            f"Dataset is missing mandatory slices: {sorted(missing_mandatory)}"
        )

    if len(examples) != manifest.examples_count:
        raise DatasetValidationError(
            f"Example count mismatch: manifest declares {manifest.examples_count}, but {len(examples)} examples were loaded"
        )

    return manifest, tuple(examples)


def validate_dataset(dataset_path: str | Path) -> dict[str, Any]:
    """Validate a dataset and return a summary report dict."""
    try:
        manifest, examples = load_dataset(dataset_path)
        return {
            "valid": True,
            "dataset_id": manifest.dataset_id,
            "version": manifest.version,
            "role": manifest.role,
            "canonical_key": manifest.canonical_key,
            "values": list(manifest.values),
            "examples_count": len(examples),
            "mandatory_slices_count": len(manifest.mandatory_slices),
        }
    except DatasetValidationError as err:
        return {
            "valid": False,
            "error": str(err),
        }
