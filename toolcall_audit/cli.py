"""Command line entry point: replay a session file and print a summary table."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from toolcall_audit import __version__
from toolcall_audit.models import SessionReport
from toolcall_audit.policy import load_policy
from toolcall_audit.replay import load_session, replay

DEFAULT_POLICY = Path(__file__).resolve().parents[1] / "policy" / "default.yaml"


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``toolcall-audit`` command."""
    parser = argparse.ArgumentParser(
        prog="toolcall-audit",
        description="Replay a recorded agent session against a tool policy.",
    )
    parser.add_argument("session", help="path to the recorded session JSON file")
    parser.add_argument(
        "--policy",
        default=str(DEFAULT_POLICY),
        help="path to the YAML policy (default: the bundled policy)",
    )
    parser.add_argument(
        "--only",
        choices=("all", "allow", "review", "deny"),
        default="all",
        help="show only verdicts with this decision",
    )
    parser.add_argument("--version", action="version", version=f"toolcall-audit {__version__}")
    return parser


def format_table(report: SessionReport, only: str = "all") -> str:
    """Render the verdicts as a fixed-width table plus a summary line."""
    rows = [v for v in report.verdicts if only == "all" or v.decision == only]
    header = ("CALL", "TOOL", "DECISION", "RULE")
    body = [(v.call_id, v.tool, v.decision, v.rule) for v in rows]
    widths = [max(len(header[i]), *(len(row[i]) for row in body)) if body else len(header[i]) for i in range(4)]

    def line(cells: tuple[str, ...]) -> str:
        return "  ".join(cell.ljust(widths[i]) for i, cell in enumerate(cells)).rstrip()

    out = [line(header), line(tuple("-" * w for w in widths))]
    out.extend(line(row) for row in body)
    out.append("")
    out.append(
        f"{report.session_id} ({report.agent}): {report.total} calls, "
        f"{report.allowed} allow, {report.review} review, {report.denied} deny"
    )
    if report.drift:
        out.append(f"drift: {', '.join(report.drift)}")
    else:
        out.append("drift: none")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    """Run the replay and print the table; returns a shell exit code."""
    args = build_parser().parse_args(argv)
    try:
        session = load_session(args.session)
        policy = load_policy(args.policy)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    report = replay(session, policy)
    print(format_table(report, only=args.only))
    return 1 if report.denied else 0


if __name__ == "__main__":
    raise SystemExit(main())
