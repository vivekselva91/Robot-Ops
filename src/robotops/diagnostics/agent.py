"""Live ROS 2 diagnostic and uptime agent."""

from __future__ import annotations

import json

from ..llm import ClaudeClient
from ..schemas import AgentReport, Finding
from .model import DiagnosticStatus, aggregate, stale_nodes
from .sim import generate_stream

SYSTEM = """You are an SRE for a robot fleet reading ROS 2 diagnostics.
You get per-node uptime, failure counts, MTBF and resource usage.
Correlate failures across nodes: a node that goes stale at the same time another
node's CPU saturates is usually a victim, not the cause.

Return JSON:
{"headline": str, "fleet_state": "healthy"|"degraded"|"critical",
 "correlations": [{"observation": str, "implication": str}],
 "watch_list": [str], "actions": [str]}"""

CRITICAL_NODES = {"camera_driver", "lidar_driver", "motor_bridge"}


def analyze(
    statuses: list[DiagnosticStatus] | None = None,
    *,
    client: ClaudeClient | None = None,
    uptime_target: float = 99.0,
) -> AgentReport:
    statuses = statuses or generate_stream()
    client = client or ClaudeClient()
    health = aggregate(statuses)
    now = max(status.stamp for status in statuses)
    stale = stale_nodes(statuses, now=now)

    findings: list[Finding] = []
    for name, node in sorted(health.items()):
        if node.uptime_pct < uptime_target:
            findings.append(
                Finding(
                    severity="critical" if name in CRITICAL_NODES else "warning",
                    title=f"{name} below uptime target",
                    detail=(
                        f"Uptime {node.uptime_pct}% against a {uptime_target}% target across "
                        f"{len(node.failures)} failure episode(s); MTBF "
                        + (f"{node.mtbf_seconds}s." if node.mtbf_seconds else "not yet measurable.")
                    ),
                    source="rule",
                    evidence=node.to_dict(),
                )
            )
        if node.cpu and max(node.cpu) > 85:
            findings.append(
                Finding(
                    severity="warning",
                    title=f"{name} CPU saturation",
                    detail=f"Peak CPU {round(max(node.cpu), 1)}% during the window.",
                    source="rule",
                    evidence={"peak_cpu_pct": round(max(node.cpu), 1)},
                )
            )
    for name in stale:
        findings.append(
            Finding(
                severity="critical",
                title=f"{name} heartbeat stale",
                detail="No diagnostic message within the heartbeat timeout.",
                source="rule",
            )
        )

    table = [node.to_dict() for node in health.values()]
    verdict = client.ask_json(
        SYSTEM,
        "Per-node health over the window:\n"
        f"{json.dumps(table, indent=2)}\n\n"
        f"Currently stale nodes: {stale or 'none'}",
        fallback={
            "headline": "Fleet degraded: camera driver dropped out twice.",
            "fleet_state": "degraded",
            "correlations": [
                {
                    "observation": "camera_driver went stale while ekf_localization CPU was above 90%.",
                    "implication": "The dropout is likely CPU starvation, not a camera fault.",
                }
            ],
            "watch_list": ["camera_driver", "ekf_localization"],
            "actions": ["Pin ekf_localization to its own core and re-run the window."],
        },
    )

    for correlation in verdict.get("correlations") or []:
        findings.append(
            Finding(
                severity="warning",
                title=correlation.get("observation", "Correlation"),
                detail=correlation.get("implication", ""),
                source="claude",
            )
        )

    worst = min((n.uptime_pct for n in health.values()), default=100.0)
    return AgentReport(
        agent="ROS 2 diagnostics and uptime agent",
        summary=verdict.get("headline", "Diagnostics window analyzed."),
        findings=findings,
        metrics={
            "nodes_tracked": len(health),
            "fleet_state": verdict.get("fleet_state", "unknown"),
            "worst_node_uptime_pct": worst,
            "stale_nodes": len(stale),
        },
        recommendations=list(verdict.get("actions") or []),
    )
