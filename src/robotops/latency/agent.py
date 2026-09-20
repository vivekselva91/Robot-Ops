"""Edge-to-cloud latency profiler."""

from __future__ import annotations

import json

from ..llm import ClaudeClient
from ..schemas import AgentReport, Finding
from .sim import generate_traces
from .trace import Trace, dominant_stage, summarize

SYSTEM = """You are a distributed-systems engineer profiling a teleoperation pipeline.
Stages run: sensor_acquire, serialize, uplink, cloud_inference, downlink, deserialize, actuate.

Attribute latency correctly:
- high p95 with low p50 in uplink or downlink means network jitter
- high p50 across serialize and deserialize means payload or encoding overhead
- occasional large cloud_inference spikes mean cold starts or queueing, not network
- steady growth across all stages means the host is resource starved

Return JSON:
{"headline": str, "primary_bottleneck": str, "attribution": str,
 "secondary_factors": [str], "actions": [str], "expected_saving_ms": number}"""


def analyze(
    traces: list[Trace] | None = None,
    *,
    client: ClaudeClient | None = None,
    budget_ms: float = 150.0,
) -> AgentReport:
    traces = traces or generate_traces()
    client = client or ClaudeClient()
    summary = summarize(traces, budget_ms=budget_ms)
    worst_stage, worst_stats = dominant_stage(summary)

    findings: list[Finding] = []
    if summary["budget_violation_pct"] > 1.0:
        findings.append(
            Finding(
                severity="critical" if summary["budget_violation_pct"] > 5 else "warning",
                title="Round trips exceeding the control budget",
                detail=(
                    f"{summary['budget_violation_pct']}% of traces exceeded the {budget_ms} ms "
                    f"budget; p99 is {summary['total']['p99']} ms."
                ),
                source="rule",
                evidence=summary["total"],
            )
        )
    for stage, stats in summary["stages"].items():
        if stats["jitter_p95_minus_p50"] > 20:
            findings.append(
                Finding(
                    severity="warning",
                    title=f"{stage} is jittery",
                    detail=(
                        f"p50 {stats['p50']} ms but p95 {stats['p95']} ms, a "
                        f"{stats['jitter_p95_minus_p50']} ms spread."
                    ),
                    source="rule",
                    evidence=stats,
                )
            )

    verdict = client.ask_json(
        SYSTEM,
        "Stage percentiles (ms):\n"
        f"{json.dumps(summary['stages'], indent=2)}\n\n"
        f"End-to-end: {json.dumps(summary['total'])}\n"
        f"Budget {budget_ms} ms, violated on {summary['budget_violation_pct']}% of traces.\n\n"
        "Five worst traces:\n"
        f"{json.dumps(summary['worst_traces'], indent=2)}",
        fallback={
            "headline": f"{worst_stage} dominates the p95 path.",
            "primary_bottleneck": worst_stage,
            "attribution": (
                f"{worst_stage} contributes {worst_stats['share_of_p95_pct']}% of p95 latency "
                f"with a {worst_stats['jitter_p95_minus_p50']} ms spread between p50 and p95."
            ),
            "secondary_factors": ["Periodic cloud_inference spikes consistent with cold starts."],
            "actions": [
                "Pin a warm model replica per region to remove cold-start spikes.",
                "Move teleop command frames to a lower-latency transport than the video path.",
            ],
            "expected_saving_ms": round(worst_stats["p95"] - worst_stats["p50"], 1),
        },
    )

    findings.append(
        Finding(
            severity="info",
            title=f"Primary bottleneck: {verdict.get('primary_bottleneck', worst_stage)}",
            detail=verdict.get("attribution", ""),
            source="claude",
            evidence={"expected_saving_ms": verdict.get("expected_saving_ms")},
        )
    )

    return AgentReport(
        agent="Edge-to-cloud latency profiler",
        summary=verdict.get("headline", "Latency window analyzed."),
        findings=findings,
        metrics={
            "traces": summary["traces"],
            "p50_ms": summary["total"]["p50"],
            "p95_ms": summary["total"]["p95"],
            "p99_ms": summary["total"]["p99"],
            "budget_violation_pct": summary["budget_violation_pct"],
        },
        recommendations=list(verdict.get("actions") or []),
    )
