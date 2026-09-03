"""CLI entry points for governed RAG evaluation.

Supports subcommands per Task 4 Step 9:
- validate-dataset --dataset <dir>
- preflight --dataset <dir> --config <file> --mode [retrieval|full]
- run --dataset <dir> --config <file> --mode [retrieval|full] --output-dir <dir>
- compare --baseline <run-dir> --candidate <run-dir> --output <report-json>
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from backend.rag.evaluation.artifacts import load_run_artifact
from backend.rag.evaluation.comparison import compare_runs
from backend.rag.evaluation.dataset import load_dataset, load_run_config
from backend.rag.evaluation.runner import EvaluationRunner, RunMode
from backend.rag.evaluation.runtime import preflight


def cmd_validate_dataset(args: argparse.Namespace) -> int:
    """Validate dataset manifest and JSONL examples."""
    try:
        dataset_path = Path(args.dataset)
        dataset = load_dataset(dataset_path)
        print(
            f"Dataset '{dataset.manifest.dataset_id}' v{dataset.manifest.version} "
            f"is valid ({len(dataset.examples)} examples, role={dataset.manifest.role.value})."
        )
        return 0
    except Exception as err:
        print(f"Error validating dataset: {err}", file=sys.stderr)
        return 1


def cmd_preflight(args: argparse.Namespace) -> int:
    """Run preflight environment and contract checks."""
    try:
        preflight(
            dataset=args.dataset,
            config=args.config,
            mode=args.mode,
        )
        print(
            f"Preflight check PASSED for dataset '{args.dataset}', "
            f"config '{args.config}', mode '{args.mode}'."
        )
        return 0
    except Exception as err:
        print(f"Preflight FAILED: {err}", file=sys.stderr)
        return 1


def cmd_run(args: argparse.Namespace) -> int:
    """Execute evaluation run in retrieval or full mode."""
    try:
        dataset = load_dataset(Path(args.dataset))
        config = load_run_config(Path(args.config))
        mode = RunMode(args.mode)

        output_dir = Path(args.output_dir) if args.output_dir else None
        runner = EvaluationRunner(dataset=dataset, config=config)
        artifact = runner.run(
            mode=mode,
            output_dir=output_dir,
            baseline_run_id=getattr(args, "baseline_run_id", None),
        )


        print(
            f"Run completed: run_id={artifact.run_record['run_id']} "
            f"state={artifact.run_record['state']} "
            f"eligible={artifact.run_record['eligible_count']} "
            f"mode={mode.value}"
        )
        if output_dir:
            print(f"Artifacts persisted to {output_dir}")
        return 0
    except Exception as err:
        print(f"Run FAILED: {err}", file=sys.stderr)
        return 1


def cmd_compare(args: argparse.Namespace) -> int:
    """Compare baseline and candidate run artifacts under D5 gates."""
    try:
        baseline_path = Path(args.baseline)
        candidate_path = Path(args.candidate)

        baseline_artifact = load_run_artifact(baseline_path)
        candidate_artifact = load_run_artifact(candidate_path)

        result = compare_runs(
            baseline_artifact.run_record,
            baseline_artifact.example_records,
            candidate_artifact.run_record,
            candidate_artifact.example_records,
        )

        report = {
            "state": result.state.value,
            "paired_deltas": result.paired_deltas,
            "slice_deltas": result.slice_deltas,
            "failed_gates": list(result.failed_gates),
            "candidate_changes": result.candidate_changes,
            "uncertainty": result.uncertainty,
            "reason": result.reason,
        }

        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(
            f"Comparison completed: state={result.state.value} "
            f"failed_gates={list(result.failed_gates)} "
            f"output={output_path}"
        )
        return 0
    except Exception as err:
        print(f"Comparison FAILED: {err}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    """Build top-level argument parser with subcommands."""
    parser = argparse.ArgumentParser(
        description="Governed RAG Evaluation CLI (R2 Harness v0.1)"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # validate-dataset
    parser_val = subparsers.add_parser("validate-dataset", help="Validate dataset schema")
    parser_val.add_argument("--dataset", required=True, help="Path to dataset directory")

    # preflight
    parser_pref = subparsers.add_parser("preflight", help="Run preflight environment checks")
    parser_pref.add_argument("--dataset", required=True, help="Path to dataset directory")
    parser_pref.add_argument("--config", required=True, help="Path to run config JSON file")
    parser_pref.add_argument(
        "--mode",
        choices=["retrieval", "full"],
        default="retrieval",
        help="Evaluation mode (default: retrieval)",
    )

    # run
    parser_run = subparsers.add_parser("run", help="Execute evaluation run")
    parser_run.add_argument("--dataset", required=True, help="Path to dataset directory")
    parser_run.add_argument("--config", required=True, help="Path to run config JSON file")
    parser_run.add_argument(
        "--mode",
        choices=["retrieval", "full"],
        default="retrieval",
        help="Evaluation mode (default: retrieval)",
    )
    parser_run.add_argument("--output-dir", help="Directory to save run artifacts")
    parser_run.add_argument(
        "--baseline-run-id",
        help="Optional baseline run_id when evaluating candidate",
    )


    # compare
    parser_comp = subparsers.add_parser("compare", help="Compare baseline and candidate runs")
    parser_comp.add_argument("--baseline", required=True, help="Path to baseline run directory")
    parser_comp.add_argument("--candidate", required=True, help="Path to candidate run directory")
    parser_comp.add_argument("--output", required=True, help="Path to output comparison report JSON")

    return parser


def main(argv: list[str] | None = None) -> int:
    """Main CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate-dataset":
        return cmd_validate_dataset(args)
    elif args.command == "preflight":
        return cmd_preflight(args)
    elif args.command == "run":
        return cmd_run(args)
    elif args.command == "compare":
        return cmd_compare(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
