"""Console and markdown rendering for agent reports."""

from __future__ import annotations

import json

from .schemas import AgentReport

_MARK = {"info": "[ok]", "warning": "[warn]", "critical": "[CRIT]"}


def print_report(report: AgentReport) -> None:
    print(f"\n=== {report.agent} ===")
    print(report.summary)
    if report.metrics:
        print("\nMetrics")
        for key, value in report.metrics.items():
            print(f"  {key}: {value}")
    if report.findings:
        print("\nFindings")
        for finding in report.findings:
            print(f"  {_MARK.get(finding.severity, '[?]')} {finding.title} ({finding.source})")
            print(f"      {finding.detail}")
    if report.recommendations:
        print("\nRecommended actions")
        for item in report.recommendations:
            print(f"  - {item}")
    print()


def to_markdown(report: AgentReport) -> str:
    lines = [f"# {report.agent}", "", report.summary, ""]
    if report.metrics:
        lines += ["## Metrics", ""]
        lines += [f"- **{k}**: {v}" for k, v in report.metrics.items()]
        lines.append("")
    if report.findings:
        lines += ["## Findings", ""]
        for finding in report.findings:
            lines.append(f"### {finding.severity.upper()}: {finding.title}")
            lines += [finding.detail, ""]
            if finding.evidence:
                lines += ["```json", json.dumps(finding.evidence, indent=2), "```", ""]
    if report.recommendations:
        lines += ["## Recommended actions", ""]
        lines += [f"{i}. {r}" for i, r in enumerate(report.recommendations, 1)]
    return "\n".join(lines) + "\n"
