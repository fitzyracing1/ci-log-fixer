"""Command-line interface for ci-log-fixer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ci_log_fixer import __version__
from ci_log_fixer.analyze import analyze


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci-log-fixer",
        description=(
            "Read a failing GitHub Actions log and report common causes "
            "with a concrete suggested fix. Prints a report; never overwrites the log."
        ),
    )
    parser.add_argument(
        "log",
        nargs="?",
        default="-",
        help="Path to a job log, or - to read stdin (the default)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the report to LOG.tidy.txt (never overwrites LOG)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"ci-log-fixer {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.log == "-":
        if args.write:
            print(
                "ci-log-fixer: --write needs a file path, not stdin",
                file=sys.stderr,
            )
            return 2
        text = sys.stdin.read()
        source = "stdin"
        path = None
    else:
        path = Path(args.log)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as err:
            print(f"ci-log-fixer: cannot read {path}: {err}", file=sys.stderr)
            return 1
        source = str(path)

    result = analyze(text, source=source)
    report = result.report()
    if args.write and path is not None:
        dest = path.with_name(path.stem + ".tidy.txt")
        dest.write_text(report, encoding="utf-8")
        sys.stderr.write(f"Wrote {dest}\n")
    else:
        sys.stdout.write(report)
        if report and not report.endswith("\n"):
            sys.stdout.write("\n")
    return 0 if not result.findings else 1


if __name__ == "__main__":
    sys.exit(main())
