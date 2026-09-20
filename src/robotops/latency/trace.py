"""Span recording and percentile math for an edge-to-cloud teleop pipeline."""

from __future__ import annotations

import statistics
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

STAGES = [
    "sensor_acquire",
    "serialize",
    "uplink",
    "cloud_inference",
    "downlink",
    "deserialize",
    "actuate",
]


@dataclass
class Trace:
    """One command round trip, stage name -> milliseconds spent."""

    trace_id: str
    t_start: float
    stages: dict[str, float]

    @property
    def total_ms(self) -> float:
        return round(sum(self.stages.values()), 2)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return round(ordered[index], 2)


def summarize(traces: Iterable[Trace], budget_ms: float = 150.0) -> dict[str, Any]:
    traces = list(traces)
    totals = [t.total_ms for t in traces]
    per_stage = {
        stage: [t.stages.get(stage, 0.0) for t in traces] for stage in STAGES
    }
    stage_stats = {
        stage: {
            "p50": percentile(values, 50),
            "p95": percentile(values, 95),
            "p99": percentile(values, 99),
            "jitter_p95_minus_p50": round(percentile(values, 95) - percentile(values, 50), 2),
            "share_of_p95_pct": 0.0,
        }
        for stage, values in per_stage.items()
    }
    total_p95 = percentile(totals, 95) or 1.0
    for stats in stage_stats.values():
        stats["share_of_p95_pct"] = round(100 * stats["p95"] / total_p95, 1)

    violations = [t for t in traces if t.total_ms > budget_ms]
    return {
        "traces": len(traces),
        "total": {
            "p50": percentile(totals, 50),
            "p95": total_p95,
            "p99": percentile(totals, 99),
            "max": round(max(totals), 2) if totals else 0.0,
            "mean": round(statistics.fmean(totals), 2) if totals else 0.0,
        },
        "budget_ms": budget_ms,
        "budget_violation_pct": round(100 * len(violations) / len(traces), 2) if traces else 0.0,
        "stages": stage_stats,
        "worst_traces": [
            {"trace_id": t.trace_id, "total_ms": t.total_ms, "stages": t.stages}
            for t in sorted(traces, key=lambda t: -t.total_ms)[:5]
        ],
    }


def dominant_stage(summary: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    stages = summary["stages"]
    name = max(stages, key=lambda s: stages[s]["p95"])
    return name, stages[name]
