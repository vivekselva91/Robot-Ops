"""Slack and Discord delivery using only the standard library."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..config import Config, load_config
from ..schemas import AgentReport


def send_alert(report: AgentReport, config: Config | None = None, *, dry_run: bool = False) -> str:
    config = config or load_config()
    text = _format(report)
    targets = []
    if config.slack_webhook:
        targets.append(("slack", config.slack_webhook, {"text": text}))
    if config.discord_webhook:
        targets.append(("discord", config.discord_webhook, {"content": text}))
    if not targets or dry_run:
        print(text)
        return "printed to stdout (no webhook configured or dry run)"

    delivered = []
    for name, url, payload in targets:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                delivered.append(f"{name}:{response.status}")
        except urllib.error.URLError as exc:
            delivered.append(f"{name}:failed ({exc.reason})")
    return ", ".join(delivered)


def _format(report: AgentReport) -> str:
    icon = {"info": ":white_check_mark:", "warning": ":warning:", "critical": ":rotating_light:"}
    lines = [f"{icon.get(report.worst_severity, '')} *{report.agent}*", report.summary]
    for finding in report.findings:
        if finding.severity in ("warning", "critical"):
            lines.append(f"- *{finding.title}* — {finding.detail}")
    for item in report.recommendations[:3]:
        lines.append(f"  -> {item}")
    return "\n".join(lines)
