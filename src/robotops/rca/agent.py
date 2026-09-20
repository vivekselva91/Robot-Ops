"""Automated root cause analysis for robot incidents."""

from __future__ import annotations

import json
from typing import Any

from ..llm import ClaudeClient
from ..schemas import AgentReport, Finding
from .sim import build_incident

SYSTEM = """You are a robotics reliability engineer writing a root cause analysis.
You receive a frozen incident bundle: logs from application, middleware and kernel
layers, system metrics, and robot state snapshots from the seconds before a failure.

Work backwards from the trigger. Separate the proximate cause (what asserted the
fault) from the root cause (what made it inevitable). A watchdog firing is a symptom.
Name the layer the root cause lives in: hardware, kernel/scheduling, middleware, or
application logic. Say explicitly if the evidence does not support a confident root cause.

Return JSON:
{"title": str, "timeline": [{"t": number, "event": str}],
 "proximate_cause": str, "root_cause": str, "layer": str, "confidence": float,
 "contributing_factors": [str], "corrective_actions": [str],
 "evidence_gaps": [str]}"""


def preprocess(bundle: dict[str, Any]) -> dict[str, Any]:
    """Cheap deterministic reductions, so the model gets signal instead of noise."""
    metrics = bundle.get("metrics", [])
    peaks: dict[str, float] = {}
    for row in metrics:
        for key, value in row.items():
            if key == "t" or not isinstance(value, (int, float)):
                continue
            peaks[key] = max(peaks.get(key, float("-inf")), float(value))
    errors = [log for log in bundle["logs"] if log["lvl"] in ("ERROR", "FATAL")]
    first_error = min((log["t"] for log in errors), default=None)
    return {
        "peaks": {k: round(v, 1) for k, v in peaks.items()},
        "error_count": len(errors),
        "first_error_t": first_error,
        "seconds_from_first_error_to_trigger": (
            round(bundle["triggered_at"] - first_error, 2) if first_error is not None else None
        ),
        "sources_reporting_errors": sorted({log["src"] for log in errors}),
    }


def analyze(
    bundle: dict[str, Any] | None = None,
    *,
    client: ClaudeClient | None = None,
) -> AgentReport:
    bundle = bundle or build_incident()
    client = client or ClaudeClient()
    derived = preprocess(bundle)

    tail_logs = bundle["logs"][-40:]
    metric_tail = bundle["metrics"][-40:]
    verdict = client.ask_json(
        SYSTEM,
        f"Trigger: {bundle['trigger']} at t={bundle['triggered_at']}\n"
        f"Window: last {bundle['window_s']} s\n\n"
        f"Derived signals:\n{json.dumps(derived, indent=2)}\n\n"
        f"Logs (tail):\n{json.dumps(tail_logs, indent=2)}\n\n"
        f"Metrics (tail):\n{json.dumps(metric_tail, indent=2)}\n\n"
        f"State snapshots:\n{json.dumps(bundle['snapshots'][-6:], indent=2)}",
        fallback={
            "title": "E-stop from LiDAR watchdog during CPU starvation",
            "timeline": [
                {"t": 22.0, "event": "cpu_core3 saturates above 90%"},
                {"t": 27.0, "event": "lidar_driver reports frame timeouts"},
                {"t": 29.8, "event": "safety_monitor asserts E-stop"},
            ],
            "proximate_cause": "The LiDAR watchdog fired after scans exceeded the 50 ms deadline.",
            "root_cause": (
                "A localization thread saturated core 3, starving the LiDAR driver callback "
                "until message age crossed the watchdog threshold."
            ),
            "layer": "kernel/scheduling",
            "confidence": 0.78,
            "contributing_factors": [
                "No CPU affinity set for the localization thread.",
                "Watchdog threshold leaves no margin for scheduling jitter.",
            ],
            "corrective_actions": [
                "Pin the localization thread to a dedicated core and cap its rate.",
                "Alert on lidar_msg_age_ms trending above 35 ms before the watchdog fires.",
            ],
            "evidence_gaps": ["No per-thread scheduler trace in the bundle."],
        },
    )

    findings = [
        Finding(
            severity="critical",
            title="Proximate cause",
            detail=verdict.get("proximate_cause", ""),
            source="claude",
        ),
        Finding(
            severity="critical",
            title=f"Root cause ({verdict.get('layer', 'unknown')} layer)",
            detail=verdict.get("root_cause", ""),
            source="claude",
            evidence={"confidence": verdict.get("confidence"), **derived},
        ),
    ]
    for factor in verdict.get("contributing_factors") or []:
        findings.append(
            Finding(severity="warning", title="Contributing factor", detail=factor, source="claude")
        )
    for gap in verdict.get("evidence_gaps") or []:
        findings.append(
            Finding(severity="info", title="Evidence gap", detail=gap, source="claude")
        )

    return AgentReport(
        agent="Automated root cause analysis",
        summary=verdict.get("title", "Incident analyzed."),
        findings=findings,
        metrics={
            "trigger": bundle["trigger"],
            "logs_captured": bundle["counts"]["logs"],
            "errors_captured": bundle["counts"]["errors"],
            "lead_time_s": derived["seconds_from_first_error_to_trigger"],
            "confidence": verdict.get("confidence"),
        },
        recommendations=list(verdict.get("corrective_actions") or []),
    )
