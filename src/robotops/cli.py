"""Command line entry point: robotops <agent> [--demo] [--json] [--alert]."""

from __future__ import annotations

import argparse
import json
import sys

from .config import load_config
from .llm import ClaudeClient
from .report import print_report, to_markdown
from .schemas import AgentReport

AGENTS = ("fusion", "diagnostics", "latency", "rca", "maintenance")


def _run(name: str, client: ClaudeClient) -> AgentReport:
    if name == "fusion":
        from .fusion.agent import analyze
    elif name == "diagnostics":
        from .diagnostics.agent import analyze
    elif name == "latency":
        from .latency.agent import analyze
    elif name == "rca":
        from .rca.agent import analyze
    elif name == "maintenance":
        from .maintenance.agent import analyze
    else:  # pragma: no cover - argparse blocks this
        raise SystemExit(f"unknown agent: {name}")
    return analyze(client=client)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="robotops",
        description="Claude-powered reliability agents for robotics fleets.",
    )
    parser.add_argument("agent", choices=AGENTS, help="which agent to run")
    parser.add_argument(
        "--demo",
        action="store_true",
        help="run against the built-in synthetic scenario (default when no input is given)",
    )
    parser.add_argument("--json", action="store_true", help="emit the report as JSON")
    parser.add_argument("--markdown", metavar="PATH", help="write a markdown report to PATH")
    parser.add_argument("--alert", action="store_true", help="send the report to Slack or Discord")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="skip the Claude call and use deterministic fallbacks",
    )
    args = parser.parse_args(argv)

    config = load_config()
    client = ClaudeClient(config, offline=args.offline)
    if client.offline and not args.offline:
        print("No ANTHROPIC_API_KEY found: running with deterministic fallbacks.", file=sys.stderr)

    report = _run(args.agent, client)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_report(report)

    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as handle:
            handle.write(to_markdown(report))
        print(f"wrote {args.markdown}")

    if args.alert:
        from .diagnostics.alerts import send_alert

        print(send_alert(report, config))

    return 2 if report.worst_severity == "critical" else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
