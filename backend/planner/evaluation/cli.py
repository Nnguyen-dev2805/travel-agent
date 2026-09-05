"""Command-line entry point for the R7 planner state evaluation.

The `run-state` command replays a planner suite and writes one Markdown and
one JSON report. It needs no model provider, RAG retrieval, embedding
model, Chroma data, Docker, or network access.

Examples:
    ./.venv/bin/python -m backend.planner.evaluation.cli run-state \\
        --suite r7-state-v0.1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.planner.evaluation.models import PlannerResultState
from backend.planner.evaluation.runner import run_state_evaluation

DEFAULT_OUTPUT_DIR = Path("docs/reports/planner")
DEFAULT_SUITE_DIR = Path("docs/evaluation/fixtures/planner")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay an R7 planner state suite and write reports."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    state_parser = subparsers.add_parser(
        "run-state", help="Replay a planner suite and write reports."
    )
    state_parser.add_argument(
        "--suite",
        default="r7-state-v0.1",
        help="Suite directory name under the planner fixtures directory.",
    )
    state_parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Fixture manifest path, overriding --suite resolution.",
    )
    state_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory receiving the Markdown and JSON reports.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-state":
        manifest = args.fixture
        if manifest is None:
            manifest = DEFAULT_SUITE_DIR / args.suite / "manifest.json"
        report = run_state_evaluation(manifest, args.output_dir)
        print(f"result_state={report.result_state.value}")
        print(f"eligible_examples={report.eligible_examples}")
        print(f"output_dir={args.output_dir}")
        if report.result_state is PlannerResultState.INVALID:
            return 2
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
