"""Command-line entry point for the R9 security evaluation.

The `run-security` command replays a security suite and writes one
Markdown and one JSON report. It needs no model provider, RAG retrieval,
embedding model, Chroma data, Docker, or network access. It does need the
auth gate enabled with a synthetic token registry; otherwise the report
is `INVALID`, never a passing claim.

Example:
    AUTH_REQUIRED=true LOCAL_AUTH_TOKENS_JSON='{"owner_a":"secret-alpha-token","owner_b":"secret-beta-token"}' \\
    ./.venv/bin/python -m backend.security.evaluation.cli run-security \\
        --suite r9-security-privacy-v0.1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from backend.security.evaluation.models import SecurityResultState
from backend.security.evaluation.runner import run_security_evaluation

DEFAULT_OUTPUT_DIR = Path("docs/reports/security")
DEFAULT_SUITE_DIR = Path("docs/evaluation/fixtures/security")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Replay an R9 security suite and write reports."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    state_parser = subparsers.add_parser(
        "run-security", help="Replay a security suite and write reports."
    )
    state_parser.add_argument(
        "--suite",
        default="r9-security-privacy-v0.1",
        help="Suite directory name under the security fixtures directory.",
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
    if args.command == "run-security":
        manifest = args.fixture
        if manifest is None:
            manifest = DEFAULT_SUITE_DIR / args.suite / "manifest.json"
        report = run_security_evaluation(manifest, args.output_dir)
        print(f"result_state={report.result_state.value}")
        print(f"eligible_examples={report.eligible_examples}")
        print(f"output_dir={args.output_dir}")
        if report.result_state is SecurityResultState.INVALID:
            return 2
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
