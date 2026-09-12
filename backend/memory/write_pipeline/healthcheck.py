"""Healthcheck entry point for the background Memory worker.

ADR 0029: the worker has no HTTP surface, so its liveness is the process itself
plus a heartbeat. `run_worker` touches the heartbeat file once per completed
batch — empty polls included — so a healthy worker's file is never older than
one poll interval plus one batch duration. This module turns that signal into
a container healthcheck's exit status: fresh file, exit 0; missing or stale
file, exit 1.

Deliberately a separate process from the worker: a healthcheck that runs
inside the process it is checking cannot detect that the process is wedged,
which is the one condition "container running" cannot expose by itself.
"""

from __future__ import annotations

import sys

from backend.memory.write_pipeline.observability import touch_is_fresh

#: Exit statuses are the healthcheck contract; keep them literal.
EXIT_HEALTHY = 0
EXIT_UNHEALTHY = 1


def main(argv: list[str] | None = None) -> int:
    """Read the heartbeat and report freshness as the exit status.

    Usage: `python -m backend.memory.write_pipeline.healthcheck <path> [max_age]`

    `max_age` defaults to 30 seconds — six poll intervals at the 5-second
    default — so one wedged batch does not flap the container unhealthy, while
    a worker that has stopped polling entirely is flagged within half a
    minute. An operator with a slower poll interval overrides it to match.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print(
            "usage: python -m backend.memory.write_pipeline.healthcheck "
            "<heartbeat-path> [max-age-seconds]",
            file=sys.stderr,
        )
        return EXIT_UNHEALTHY

    path = args[0]
    try:
        max_age = float(args[1]) if len(args) > 1 else 30.0
    except ValueError:
        print(f"max-age-seconds must be a number, not {args[1]!r}", file=sys.stderr)
        return EXIT_UNHEALTHY

    if touch_is_fresh(path, max_age_seconds=max_age):
        return EXIT_HEALTHY
    print(
        f"heartbeat {path!r} is missing or older than {max_age}s",
        file=sys.stderr,
    )
    return EXIT_UNHEALTHY


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
