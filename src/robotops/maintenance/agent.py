"""Predictive maintenance copilot for actuators."""

from __future__ import annotations

import json
from collections import defaultdict

from ..llm import ClaudeClient
from ..schemas import AgentReport, Finding
from .features import MotorSample, hours_to_threshold, joint_features
from .sim import generate_telemetry

SYSTEM = """You are a maintenance engineer reviewing actuator telemetry.
Per joint you receive current draw, temperature trend, velocity tracking error and
the drift in current-per-unit-velocity against that joint's own early-life baseline.

Interpretation rules:
- rising current for the same velocity means mechanical friction: bearing, gearbox or seal
- rising temperature with flat current means cooling or ambient, not load
- rising tracking error with rising current means the joint is losing authority
- drift under about 5% is noise, not wear

Be conservative. A false alarm pulls a robot out of service for nothing.

Return JSON:
{"headline": str,
 "joints": [{"joint": str, "state": "healthy"|"watch"|"degrading",
             "interpretation": str, "suspected_component": str|null,
             "estimated_hours_remaining": number|null}],
 "actions": [str]}"""

DRIFT_WATCH_PCT = 5.0
DRIFT_ALARM_PCT = 15.0


def analyze(
    samples: list[MotorSample] | None = None,
    *,
    client: ClaudeClient | None = None,
    sample_hz: float = 0.5,
) -> AgentReport:
    samples = samples or generate_telemetry()
    client = client or ClaudeClient()

    by_joint: dict[str, list[MotorSample]] = defaultdict(list)
    for sample in samples:
        by_joint[sample.joint].append(sample)
    features = {joint: joint_features(rows) for joint, rows in sorted(by_joint.items())}

    findings: list[Finding] = []
    for joint, stats in features.items():
        drift = stats["efficiency_drift_pct"]
        if drift >= DRIFT_ALARM_PCT:
            severity = "critical"
        elif drift >= DRIFT_WATCH_PCT:
            severity = "warning"
        else:
            continue
        remaining = hours_to_threshold(stats, sample_hz)
        findings.append(
            Finding(
                severity=severity,
                title=f"{joint} drawing more current for the same velocity",
                detail=(
                    f"Current per unit velocity rose {drift}% against its own baseline "
                    f"({stats['current_per_velocity_baseline']} -> "
                    f"{stats['current_per_velocity_recent']}); peak temperature "
                    f"{stats['max_temperature_c']} C."
                    + (f" Linear extrapolation reaches the wear limit in about {remaining} "
                       "operating hours." if remaining else "")
                ),
                source="rule",
                evidence=stats,
            )
        )

    verdict = client.ask_json(
        SYSTEM,
        f"Per-joint features over the window (sample rate {sample_hz} Hz):\n"
        f"{json.dumps(features, indent=2)}",
        fallback={
            "headline": "One joint shows friction growth consistent with gearbox wear.",
            "joints": [
                {
                    "joint": joint,
                    "state": (
                        "degrading"
                        if stats["efficiency_drift_pct"] >= DRIFT_ALARM_PCT
                        else "watch"
                        if stats["efficiency_drift_pct"] >= DRIFT_WATCH_PCT
                        else "healthy"
                    ),
                    "interpretation": (
                        f"Efficiency drift {stats['efficiency_drift_pct']}% with temperature "
                        f"slope {stats['temperature_slope_per_sample']}."
                    ),
                    "suspected_component": (
                        "gearbox or bearing"
                        if stats["efficiency_drift_pct"] >= DRIFT_WATCH_PCT
                        else None
                    ),
                    "estimated_hours_remaining": hours_to_threshold(stats, sample_hz),
                }
                for joint, stats in features.items()
            ],
            "actions": ["Schedule inspection of the flagged joint at the next maintenance window."],
        },
    )

    for joint_view in verdict.get("joints") or []:
        if joint_view.get("state") in ("watch", "degrading"):
            findings.append(
                Finding(
                    severity="warning" if joint_view["state"] == "watch" else "critical",
                    title=f"{joint_view.get('joint')}: {joint_view.get('suspected_component')}",
                    detail=joint_view.get("interpretation", ""),
                    source="claude",
                    evidence={"hours_remaining": joint_view.get("estimated_hours_remaining")},
                )
            )

    return AgentReport(
        agent="Predictive maintenance copilot",
        summary=verdict.get("headline", "Actuator telemetry analyzed."),
        findings=findings,
        metrics={
            f"{joint}_drift_pct": stats["efficiency_drift_pct"] for joint, stats in features.items()
        },
        recommendations=list(verdict.get("actions") or []),
    )
