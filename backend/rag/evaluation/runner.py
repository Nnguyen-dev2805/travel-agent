"""Config-driven evaluation runner and lifecycle orchestration for R2.

Per the approved RAG repair plan (Task 4 Step 8):
- Executes retrieval-only or full (retrieval + generation + judge) evaluation.
- Runs role-independently: records behavior identity, not experiment role.
- Computes per-example metrics, aggregate metrics, and mandatory-slice metrics.
- Determines D5 result states: PASS, FAIL, INCONCLUSIVE, or INVALID.
- Emits standard RunArtifact with run.json and examples.jsonl.
"""

from __future__ import annotations

import logging
import subprocess
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from backend.rag.evaluation.artifacts import write_run_artifacts, RunArtifact
from backend.rag.evaluation.judge import (
    JUDGE_DIMENSIONS,
    JudgeAdapter,
    JudgeResult,
)
from backend.rag.evaluation.metrics import (
    aggregate_retrieval_metrics,
    compute_retrieval_metrics,
)
from backend.rag.evaluation.models import (
    EvaluationDataset,
    EvaluationExample,
    JudgeConfig,
    ResultState,
    RunConfig,
)
from backend.rag.evaluation.runtime import CurrentRuntimeAdapter

logger = logging.getLogger("rag_evaluation_runner")


class RunMode(str, Enum):
    """Execution mode of the evaluation runner."""

    RETRIEVAL = "retrieval"
    FULL = "full"


def _get_git_info() -> tuple[str, bool, str]:
    """Return (code_revision, dirty_working_tree, git_short_sha)."""
    try:
        rev = (
            subprocess.check_output(
                ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )
    except Exception:
        rev = "unknown"

    try:
        status = (
            subprocess.check_output(
                ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
            )
            .decode("utf-8")
            .strip()
        )
        dirty = bool(status)
    except Exception:
        dirty = True

    short_sha = rev[:7] if rev != "unknown" else "0000000"

    return rev, dirty, short_sha


def _judge_config_dict(judge: Any) -> dict[str, Any] | None:
    if judge is None:
        return None
    if isinstance(judge, Mapping):
        return dict(judge)
    if isinstance(judge, JudgeConfig):
        return {
            "model": judge.model,
            "prompt_id": judge.prompt_id,
            "rubric_id": judge.rubric_id,
            "schema_version": judge.schema_version,
            "temperature": judge.temperature,
        }
    return None


class EvaluationRunner:
    """Config-driven runner executing governed RAG evaluation."""

    def __init__(
        self,
        dataset: EvaluationDataset,
        config: RunConfig,
        runtime: Any = None,
        judge_adapter: Any = None,
        baseline_run_id: str | None = None,
    ) -> None:
        self.dataset = dataset
        self.config = config
        self.runtime = runtime or CurrentRuntimeAdapter(config=config)
        self.judge_adapter = judge_adapter
        self.baseline_run_id = baseline_run_id
        if self.judge_adapter is None and self.config.judge is not None:
            self.judge_adapter = JudgeAdapter(config=self.config.judge)


    def _determine_result_state(
        self,
        eligible_records: Sequence[Mapping[str, Any]],
        slice_metrics: Mapping[str, Any],
        answer_metrics: Mapping[str, Any] | None,
        mode: RunMode,
    ) -> tuple[ResultState, tuple[str, ...]]:
        """Determine final D5 result state and failed gate labels.

        INVALID, never PASS. A real gate regression on valid evidence is
        FAIL; valid-but-weak evidence stays INCONCLUSIVE; otherwise PASS.
        """
        failed_gates: list[str] = []

        # 1. Invalid retrieval/infrastructure evidence invalidates the run
        for record in eligible_records:
            rec_metrics = record.get("metrics", {})
            rec_labels = record.get("failure_labels", [])
            rec_errors = record.get("errors", [])
            if (
                rec_metrics.get("invalid_evidence_count", 0) > 0
                or "infrastructure_failure" in rec_labels
                or any("retrieval_error" in err for err in rec_errors)
            ):
                if "infrastructure_failure" in rec_labels:
                    if "infrastructure_failure" not in failed_gates:
                        failed_gates.append("infrastructure_failure")
                return ResultState.INVALID, tuple(failed_gates)


        # A judged run requires judge validity on every eligible example.
        if mode is RunMode.FULL:
            if answer_metrics is None:
                return ResultState.INVALID, tuple(failed_gates)
            if any(record.get("judge_valid") is not True for record in eligible_records):
                return ResultState.INVALID, tuple(failed_gates)
            for dimension in ("groundedness", "correctness"):
                key = f"mean_{dimension}"
                if key in answer_metrics and answer_metrics[key] < 4.0:
                    failed_gates.append(f"{key}_minimum")
            if failed_gates:
                return ResultState.FAIL, tuple(failed_gates)

        # Mandatory slices below the manifest minimum are INCONCLUSIVE.
        manifest = self.dataset.manifest
        below_minimum = [
            slice_name
            for slice_name in manifest.mandatory_slices
            if slice_metrics.get(slice_name, {}).get("eligible_count", 0)
            < manifest.min_examples_per_slice
        ]
        if below_minimum:
            return ResultState.INCONCLUSIVE, tuple(failed_gates)

        if not eligible_records:
            return ResultState.INVALID, tuple(failed_gates)

        return ResultState.PASS, tuple(failed_gates)

    def run(
        self,
        mode: RunMode | str = RunMode.RETRIEVAL,
        output_dir: Path | str | None = None,
        baseline_run_id: str | None = None,
    ) -> RunArtifact:
        """Execute the evaluation run over all dataset examples."""
        run_mode = RunMode(mode)
        effective_baseline_id = baseline_run_id or self.baseline_run_id
        started_at = datetime.now(timezone.utc).isoformat()

        rev, dirty, short_sha = _get_git_info()
        ts_compact = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        run_id = f"rag-{self.config.config_id}-{ts_compact}-{short_sha}"


        max_k = max(self.config.retrieval_k_values)
        example_records: list[dict[str, Any]] = []

        for example in self.dataset.examples:
            t0 = time.perf_counter()
            errors: list[str] = []
            failure_labels: list[str] = []

            # 1. Retrieval
            try:
                ranked_evidence = self.runtime.retrieve(example.question, top_k=max_k)
                ranked_ids = [item.chunk_id for item in ranked_evidence]
            except Exception as err:
                logger.error(f"Error retrieving for {example.example_id}: {err}")
                ranked_evidence = []
                ranked_ids = []
                errors.append(f"retrieval_error: {err}")
                failure_labels.append("infrastructure_failure")

            # 2. Compute retrieval metrics
            metrics = compute_retrieval_metrics(
                example, ranked_evidence, self.config.retrieval_k_values
            )
            if "infrastructure_failure" in failure_labels:
                metrics["invalid_evidence_count"] = metrics.get("invalid_evidence_count", 0) + 1

            if not ranked_evidence and example.expected_document_ids:
                if "infrastructure_failure" not in failure_labels:
                    failure_labels.append("retrieval_miss")
            elif metrics.get(f"hit@{self.config.primary_k}") == 0:
                failure_labels.append("retrieval_miss")
            if metrics.get("invalid_evidence_count", 0) > 0:
                failure_labels.append("invalid_evidence")

            # 3. Optional generation & judging
            answer_text: str | None = None
            context_ids: list[str] | None = None
            citations_list: list[dict[str, Any]] | None = None
            judge_valid: bool | None = None
            judge_scores: dict[str, int] | None = None

            if run_mode is RunMode.FULL:
                try:
                    generated, context_evidence = self.runtime.generate(
                        example.question, top_k=self.config.generation_context_top_k
                    )
                    answer_text = generated.reply
                    context_ids = [item.chunk_id for item in context_evidence]
                    citations_list = [
                        {
                            "title": c.title,
                            "url": c.url,
                            "evidence_ids": list(c.evidence_ids),
                        }
                        for c in generated.citations
                    ]

                    # Spec check 10: Citation cannot map to retrieved evidence -> citation_mismatch
                    # Citations must map to context_evidence (used by generation)
                    available_evidence = list(context_evidence)
                    if generated.citations:
                        for c in generated.citations:
                            matched = False
                            for ev_item in available_evidence:
                                if c.url and ev_item.url == c.url:
                                    matched = True
                                    break
                                if c.title and ev_item.title == c.title:
                                    matched = True
                                    break
                                if any(eid == ev_item.chunk_id for eid in c.evidence_ids):
                                    matched = True
                                    break
                            if not matched:
                                failure_labels.append("citation_mismatch")
                                break

                except Exception as err:
                    logger.error(f"Generation error for {example.example_id}: {err}")
                    errors.append(f"generation_error: {err}")
                    failure_labels.append("generation_error")

                # Judge
                if self.judge_adapter is not None and answer_text is not None:
                    try:
                        judge_res = self.judge_adapter.score(
                            question=example.question,
                            answer=answer_text,
                            evidence=context_evidence,
                            reference_answer=example.reference_answer,
                        )
                        judge_valid = judge_res.judge_valid
                        judge_scores = judge_res.scores
                        if not judge_valid:
                            failure_labels.append("judge_invalid")
                            if judge_res.error:
                                errors.append(f"judge_error: {judge_res.error}")
                        else:
                            # Spec check 11: Material unsupported answer claim -> unsupported_claim
                            if (
                                judge_scores.get("groundedness", 5) < 3
                                or judge_res.failure_label == "unsupported_claim"
                            ):
                                failure_labels.append("unsupported_claim")
                    except Exception as err:
                        logger.error(f"Judge error for {example.example_id}: {err}")
                        judge_valid = False
                        failure_labels.append("judge_invalid")
                        errors.append(f"judge_error: {err}")
                else:
                    judge_valid = False
                    failure_labels.append("judge_invalid")
                    errors.append("judge_not_configured_or_answer_missing")

            duration = round(time.perf_counter() - t0, 4)

            # Record structured ranked evidence for auditability
            structured_ranked_evidence = [
                {
                    "chunk_id": item.chunk_id,
                    "document_id": item.document_id,
                    "title": item.title,
                    "url": item.url,
                    "score": item.score,
                    "text_excerpt": item.text[:200] if item.text else "",
                }
                for item in ranked_evidence
            ]

            rec: dict[str, Any] = {
                "example_id": example.example_id,
                "eligible": True,
                "slices": list(example.slices),
                "category": example.category,
                "expected_document_ids": list(example.expected_document_ids),
                "expected_source_urls": list(example.expected_source_urls),
                "ranked_evidence_ids": ranked_ids,
                "ranked_evidence": structured_ranked_evidence,
                "context_evidence_ids": context_ids,
                "answer": answer_text,
                "reference_answer": example.reference_answer,
                "citations": citations_list,

                "metrics": metrics,
                "judge_valid": judge_valid,
                "failure_labels": sorted(set(failure_labels)),
                "timing_seconds": duration,
                "errors": errors,
            }
            if judge_scores is not None:
                rec["judge_scores"] = judge_scores

            example_records.append(rec)


        # 4. Aggregations
        eligible_records = [r for r in example_records if r.get("eligible")]
        per_example_metrics = [r["metrics"] for r in eligible_records]
        aggregate_metrics = aggregate_retrieval_metrics(
            per_example_metrics, self.config.retrieval_k_values
        )

        # 5. Slice metrics
        manifest = self.dataset.manifest
        all_slices = set(manifest.mandatory_slices)
        for r in eligible_records:
            all_slices.update(r.get("slices", []))

        slice_metrics: dict[str, Any] = {}
        for s in sorted(all_slices):
            slice_recs = [r for r in eligible_records if s in r.get("slices", [])]
            slice_m = aggregate_retrieval_metrics(
                [r["metrics"] for r in slice_recs], self.config.retrieval_k_values
            )
            slice_metrics[s] = {"eligible_count": len(slice_recs), **slice_m}

        # 6. Answer metrics (full mode only)
        answer_metrics: dict[str, Any] | None = None
        judge_valid_count = sum(1 for r in eligible_records if r.get("judge_valid") is True)
        judge_invalid_count = sum(1 for r in eligible_records if r.get("judge_valid") is False)

        if run_mode is RunMode.FULL:
            answer_metrics = {}
            for dim in JUDGE_DIMENSIONS:
                dim_scores = [
                    r["judge_scores"][dim]
                    for r in eligible_records
                    if r.get("judge_scores") and dim in r["judge_scores"]
                ]
                if dim_scores:
                    answer_metrics[f"mean_{dim}"] = round(
                        sum(dim_scores) / len(dim_scores), 4
                    )
                else:
                    answer_metrics[f"mean_{dim}"] = None

        # 7. State determination
        state, failed_gates = self._determine_result_state(
            eligible_records, slice_metrics, answer_metrics, run_mode
        )
        completed_at = datetime.now(timezone.utc).isoformat()

        # Aggregate failure counts and errors across examples
        failure_counts: dict[str, int] = {}
        all_errors: list[str] = []
        for r in eligible_records:
            for fl in r.get("failure_labels", []):
                failure_counts[fl] = failure_counts.get(fl, 0) + 1
            all_errors.extend(r.get("errors", []))

        total_timing_seconds = sum(r.get("timing_seconds", 0.0) for r in eligible_records)

        # 8. Build Run Record
        run_record: dict[str, Any] = {
            "run_id": run_id,
            "started_at": started_at,
            "completed_at": completed_at,
            "state": state.value,
            "failed_gates": list(failed_gates),
            "dataset_id": manifest.dataset_id,
            "dataset_version": manifest.version,
            "dataset_role": manifest.role.value,
            "manifest_id": manifest.dataset_id,
            "manifest_version": manifest.version,
            "relevance_contract": manifest.relevance_contract,
            "eligible_count": len(eligible_records),
            "invalid_count": sum(
                1
                for r in eligible_records
                if r.get("metrics", {}).get("invalid_evidence_count", 0) > 0
                or "infrastructure_failure" in r.get("failure_labels", [])
            ),
            "skipped_count": 0,
            "judge_valid_count": judge_valid_count,
            "judge_invalid_count": judge_invalid_count,
            "code_revision": rev,
            "dirty_working_tree": dirty,
            "config_id": self.config.config_id,
            "config_version": self.config.version,
            "runtime_adapter": self.config.runtime_adapter,
            "collection_name": self.config.collection_name,
            "embedding_model": self.config.embedding_model,
            "retrieval_k_values": list(self.config.retrieval_k_values),
            "primary_k": self.config.primary_k,
            "score_semantics": self.config.score_semantics,
            "generation_context_top_k": self.config.generation_context_top_k,
            "generation_model": self.config.generation_model,
            "prompt_id": self.config.prompt_id,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
            "mandatory_slices": list(manifest.mandatory_slices),
            "min_examples_per_slice": manifest.min_examples_per_slice,
            "aggregate_metrics": aggregate_metrics,
            "slice_metrics": slice_metrics,
            "answer_metrics": answer_metrics,
            "judge_config": _judge_config_dict(self.config.judge) if run_mode is RunMode.FULL else None,
            "baseline_run_id": effective_baseline_id,
            "paired_deltas": {},
            "uncertainty": {"uncertainty_status": "not_applicable_n_lt_30"},
            "gate_decisions": {},
            "timing": {"total_seconds": round(total_timing_seconds, 4)},
            "errors": all_errors,
            "failure_counts": failure_counts,
        }

        # 9. Optional write to run subdirectory
        target_dir = None
        if output_dir is not None:
            base_dir = Path(output_dir)
            if (base_dir / "run.json").exists():
                raise FileExistsError(
                    f"Run artifact directory '{base_dir}' already exists. Overwrite is barred."
                )
            target_dir = base_dir if base_dir.name == run_id else base_dir / run_id
            if (target_dir / "run.json").exists():
                raise FileExistsError(
                    f"Run artifact directory '{target_dir}' already exists. Overwrite is barred."
                )
            target_dir.mkdir(parents=True, exist_ok=True)
            write_run_artifacts(target_dir, run_record, example_records)
            logger.info(f"Persisted run artifacts to {target_dir}")



        return RunArtifact(
            run_record=run_record,
            example_records=tuple(example_records),
            run_dir=target_dir,
        )
