"""Memory-specific CLI entry point for milestone R5.

This command replays the tracked shadow fixture and writes one Markdown and
one machine-readable JSON report. It never modifies existing RAG evaluation
commands or result formats, and it requires no model provider, embedding
model, Chroma data, Docker, or network access.

Example:
    python -m backend.memory.evaluation.cli run-shadow \\
        --fixture docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json \\
        --output-dir docs/reports/memory
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.memory.evaluation.runner import (
    MemoryEvaluationError,
    run_shadow_evaluation,
)

DEFAULT_FIXTURE = Path("docs/evaluation/fixtures/memory/r5-shadow-v0.1/manifest.json")
DEFAULT_OUTPUT_DIR = Path("docs/reports/memory")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the R5 shadow memory evaluation.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser(
        "run-shadow", help="Replay the shadow fixture and write reports."
    )
    run_parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="Fixture manifest path.",
    )
    run_parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory receiving the Markdown and JSON reports.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run-shadow":
        try:
            report = run_shadow_evaluation(args.fixture, args.output_dir)
        except MemoryEvaluationError as error:
            print(f"Invalid memory evaluation: {error}", file=sys.stderr)
            return 2
        print(f"result_state={report.result_state.value}")
        print(f"eligible_examples={report.eligible_examples}")
        print(f"output_dir={args.output_dir}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
