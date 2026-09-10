"""CLI interface for the memory write pipeline evaluation harness.

Supported commands:
  validate-dataset: Validate dataset schema, manifest, and mandatory slice coverage.
  preflight: Fast check verifying dataset integrity, dependencies, and environment.
  run: Execute an evaluation suite (safety, quality, operational, all) and output reports.
  compare: Compare candidate report against baseline report for regressions.

Exit codes:
  0: PASS (All checks and assertions passed)
  1: FAIL (One or more thresholds or assertions failed)
  2: INCONCLUSIVE (Suite execution incomplete or inconclusive)
  3: INVALID (Dataset or configuration validation failed)
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Sequence

from backend.memory.write_pipeline.evaluation.dataset import (
    load_dataset,
    validate_dataset,
)
from backend.memory.write_pipeline.evaluation.models import (
    ResultState,
    SuiteReport,
    SuiteType,
)
from backend.memory.write_pipeline.evaluation.runner import EvaluationRunner

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("travel_agent_memory_evaluation_cli")

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INCONCLUSIVE = 2
EXIT_INVALID = 3


def _state_to_exit_code(state: ResultState) -> int:
    if state == ResultState.PASS:
        return EXIT_PASS
    elif state == ResultState.FAIL:
        return EXIT_FAIL
    elif state == ResultState.INCONCLUSIVE:
        return EXIT_INCONCLUSIVE
    elif state == ResultState.INVALID:
        return EXIT_INVALID
    return EXIT_FAIL


def cmd_validate_dataset(args: argparse.Namespace) -> int:
    """Validate dataset structure, manifest, and mandatory slices."""
    dataset_path = Path(args.dataset)
    print(f"Validating dataset at: {dataset_path}")
    res = validate_dataset(dataset_path)

    if not res.get("valid"):
        print("\nDataset validation FAILED:")
        print(f"  - {res.get('error')}")
        return EXIT_INVALID

    print("\nDataset validation PASSED.")
    print(f"  Dataset ID:        {res.get('dataset_id')}")
    print(f"  Version:           {res.get('version')}")
    print(f"  Role:              {res.get('role')}")
    print(f"  Canonical Key:     {res.get('canonical_key')}")
    print(f"  Allowed Values:    {res.get('values')}")
    print(f"  Examples Count:    {res.get('examples_count')}")
    print(f"  Mandatory Slices:  {res.get('mandatory_slices_count')}")
    return EXIT_PASS


def cmd_preflight(args: argparse.Namespace) -> int:
    """Run fast preflight check on dataset and runner capabilities."""
    dataset_path = Path(args.dataset)
    print(f"Running preflight checks on: {dataset_path}")

    # 1. Dataset validation
    res = validate_dataset(dataset_path)
    if not res.get("valid"):
        print(f"Preflight FAILED: Dataset is invalid: {res.get('error')}")
        return EXIT_INVALID

    # 2. Dependency / Runner instantiation check
    try:
        runner = EvaluationRunner()
        manifest, examples = load_dataset(dataset_path)
        print(f"Preflight OK: Loaded {len(examples)} examples from dataset '{manifest.dataset_id}'.")
    except Exception as exc:
        print(f"Preflight FAILED: Could not instantiate runner or load dataset: {exc}")
        return EXIT_FAIL

    print("Preflight check PASSED.")
    return EXIT_PASS


def cmd_run(args: argparse.Namespace) -> int:
    """Execute evaluation suite(s) and produce reports."""
    dataset_path = Path(args.dataset)
    output_dir = Path(args.output_dir) if args.output_dir else None

    # Validate dataset first
    res = validate_dataset(dataset_path)
    if not res.get("valid"):
        print(f"Run aborted: Dataset is invalid: {res.get('error')}")
        return EXIT_INVALID

    if getattr(args, "baseline", False):
        from backend.memory.write_pipeline.evaluation.runner import LegacyBaselineExtractor
        runner = EvaluationRunner(model_adapter=LegacyBaselineExtractor())
    else:
        runner = EvaluationRunner()

    suite_names: list[str]
    if args.suite.lower() == "all":
        suite_names = [SuiteType.SAFETY.value, SuiteType.QUALITY.value, SuiteType.OPERATIONAL.value]
    else:
        suite_names = [args.suite.lower()]

    worst_exit_code = EXIT_PASS

    for s_name in suite_names:
        try:
            stype = SuiteType(s_name)
        except ValueError:
            print(f"Unknown suite type: {s_name}")
            return EXIT_INVALID

        print(f"\n========================================================")
        print(f"Running Suite: {stype.value.upper()}")
        print(f"========================================================")
        report = runner.run_suite(dataset_path, suite_type=stype, output_dir=output_dir)

        # Print markdown summary
        print("\n" + report.to_markdown())

        code = _state_to_exit_code(report.result_state)
        if code > worst_exit_code:
            worst_exit_code = code

    if output_dir:
        print(f"\nEvaluation reports saved to: {output_dir}")

    return worst_exit_code


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare baseline report with candidate report for non-regression."""
    baseline_path = Path(args.baseline)
    candidate_path = Path(args.candidate)

    if not baseline_path.exists():
        print(f"Baseline report not found: {baseline_path}")
        return EXIT_INVALID
    if not candidate_path.exists():
        print(f"Candidate report not found: {candidate_path}")
        return EXIT_INVALID

    try:
        baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
        candidate_data = json.loads(candidate_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Failed to read reports: {exc}")
        return EXIT_INVALID

    print(f"\n========================================================")
    print(f"Comparing Candidate against Baseline")
    print(f"Baseline:  {baseline_path}")
    print(f"Candidate: {candidate_path}")
    print(f"========================================================")

    regressions: list[str] = []

    # 1. Candidate must not have hard gate events
    candidate_gates = candidate_data.get("hard_gate_events", {})
    total_cand_gates = sum(candidate_gates.values())
    if total_cand_gates > 0:
        regressions.append(f"Candidate triggered {total_cand_gates} hard-gate violations: {candidate_gates}")

    # 2. Compare metric thresholds
    cand_metrics = candidate_data.get("metrics", {})
    base_metrics = baseline_data.get("metrics", {})

    print(f"{'Metric':<32} | {'Baseline':<10} | {'Candidate':<10} | {'Status'}")
    print("-" * 65)

    for m_name, c_metric in cand_metrics.items():
        c_val = c_metric.get("value", 0.0)
        b_metric = base_metrics.get(m_name)
        b_val = b_metric.get("value", 0.0) if b_metric else None

        if b_val is not None:
            if c_val < b_val - 1e-6:
                status = "REGRESSION"
                regressions.append(f"Metric '{m_name}' regressed from {b_val:.4f} to {c_val:.4f}")
            else:
                status = "IMPROVED/EQUAL"
            print(f"{m_name:<32} | {b_val:<10.4f} | {c_val:<10.4f} | {status}")
        else:
            print(f"{m_name:<32} | {'N/A':<10} | {c_val:<10.4f} | NEW")

    # 3. Check candidate state
    cand_state = candidate_data.get("result_state")
    if cand_state != ResultState.PASS.value:
        regressions.append(f"Candidate result_state is {cand_state}, expected PASS")

    is_passed = len(regressions) == 0

    comparison_result = {
        "baseline_file": str(baseline_path),
        "candidate_file": str(candidate_path),
        "regressions": regressions,
        "passed": is_passed,
    }

    if args.output_dir:
        out_dir = Path(args.output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "comparison-report.json").write_text(
            json.dumps(comparison_result, indent=2), encoding="utf-8"
        )
        md_content = f"# Evaluation Comparison Report\n\n- **Baseline**: `{baseline_path}`\n- **Candidate**: `{candidate_path}`\n- **Status**: {'PASS (No Regressions)' if is_passed else 'FAIL (Regressions Detected)'}\n\n"
        if regressions:
            md_content += "## Regressions\n"
            for r in regressions:
                md_content += f"- {r}\n"
        else:
            md_content += "No metric regressions or hard gate violations detected.\n"
        (out_dir / "comparison-report.md").write_text(md_content, encoding="utf-8")

    if not is_passed:
        print("\nComparison FAILED with regressions:")
        for r in regressions:
            print(f"  - {r}")
        return EXIT_FAIL

    print("\nComparison PASSED: No regressions detected.")
    return EXIT_PASS


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="memory-write-eval",
        description="Evaluation harness CLI for basic semantic memory write pipeline",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate-dataset
    p_val = subparsers.add_parser("validate-dataset", help="Validate evaluation dataset integrity")
    p_val.add_argument("--dataset", required=True, help="Path to evaluation dataset directory")

    # preflight
    p_pref = subparsers.add_parser("preflight", help="Run preflight checks on dataset and environment")
    p_pref.add_argument("--dataset", required=True, help="Path to evaluation dataset directory")
    p_pref.add_argument("--suite", default="safety", choices=["safety", "quality", "operational"], help="Suite to check")

    # run
    p_run = subparsers.add_parser("run", help="Run an evaluation suite")
    p_run.add_argument("--dataset", required=True, help="Path to evaluation dataset directory")
    p_run.add_argument(
        "--suite",
        default="safety",
        choices=["safety", "quality", "operational", "all"],
        help="Suite type to execute",
    )
    p_run.add_argument("--output-dir", default=None, help="Directory to save JSON and Markdown reports")
    p_run.add_argument(
        "--baseline",
        action="store_true",
        default=False,
        help="Run using legacy baseline extractor for compatibility comparison",
    )

    # compare
    p_comp = subparsers.add_parser("compare", help="Compare candidate report against baseline report")
    p_comp.add_argument("--baseline", required=True, help="Path to baseline suite report JSON")
    p_comp.add_argument("--candidate", required=True, help="Path to candidate suite report JSON")
    p_comp.add_argument("--output-dir", default=None, help="Directory to save comparison report")

    args = parser.parse_args(argv)

    if args.command == "validate-dataset":
        return cmd_validate_dataset(args)
    elif args.command == "preflight":
        return cmd_preflight(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "compare":
        return cmd_compare(args)

    return EXIT_INVALID


if __name__ == "__main__":
    sys.exit(main())
