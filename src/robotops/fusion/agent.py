"""Sensor-fusion sanity-check agent.

Deterministic code owns detection: it runs the EKF, tracks per-sensor residuals
and NIS, and flags windows where sensors disagree. Claude owns interpretation:
given the residual summary it names the physical cause and proposes measurement
noise adjustments. That split matters because a language model should never sit
in the hard real-time path of a state estimator.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from ..llm import ClaudeClient
from ..schemas import AgentReport, Finding
from .ekf import EKF
from .sim import SensorSample, generate_run

SYSTEM = """You are a robotics state-estimation engineer reviewing a sensor fusion run.
You are given residual statistics from an EKF fusing wheel odometry, IMU and LiDAR.
Large odometry residuals with small IMU and LiDAR residuals imply wheel slip.
Large IMU residuals alone imply bias or saturation. Large LiDAR residuals alone
imply a localization or scan-matching failure.

Return JSON with this shape:
{"diagnosis": str, "likely_cause": str, "confidence": float,
 "weight_adjustments": [{"sensor": str, "current_r": float, "suggested_r": float, "reason": str}],
 "actions": [str]}
Suggested R values must stay within 0.1x to 100x of the current value."""

DEFAULT_R = {"odom": 0.02, "imu": 0.05, "lidar": 0.04}


def _windowed_velocity(samples: list[SensorSample], dt: float, window: int = 10) -> list[float]:
    """Differentiate LiDAR position over a window, not sample to sample.

    With 2 cm position noise at 20 Hz, a single-step difference carries roughly
    0.57 m/s of noise, which swamps the signal it is meant to check. Differencing
    across `window` samples divides that noise by the window length.
    """
    velocities: list[float] = []
    for i, _ in enumerate(samples):
        start = max(0, i - window)
        span = (i - start) * dt
        if span <= 0:
            velocities.append(0.0)
            continue
        velocities.append((samples[i].lidar_position - samples[start].lidar_position) / span)
    return velocities


def _cross_checks(samples: list[SensorSample], dt: float, threshold: float = 0.25) -> dict[str, Any]:
    """Compare sensors against each other, not against the fused state.

    A confident but wrong sensor drags the filter toward itself, which shrinks its
    own residual and inflates everyone else's. Pairwise agreement is what actually
    identifies the liar: the sensor that disagrees with both others is the outlier.
    """
    lidar_velocity = _windowed_velocity(samples, dt)

    pairs = {"odom_vs_imu": [], "odom_vs_lidar": [], "imu_vs_lidar": []}
    divergent_spans: list[tuple[float, float]] = []
    span_start: float | None = None
    for sample, lidar_v in zip(samples, lidar_velocity):
        pairs["odom_vs_imu"].append(abs(sample.odom_velocity - sample.imu_velocity))
        pairs["odom_vs_lidar"].append(abs(sample.odom_velocity - lidar_v))
        pairs["imu_vs_lidar"].append(abs(sample.imu_velocity - lidar_v))
        diverging = pairs["odom_vs_imu"][-1] > threshold
        if diverging and span_start is None:
            span_start = sample.t
        elif not diverging and span_start is not None:
            divergent_spans.append((round(span_start, 2), round(sample.t, 2)))
            span_start = None
    if span_start is not None:
        divergent_spans.append((round(span_start, 2), round(samples[-1].t, 2)))

    means = {name: round(statistics.fmean(values), 4) for name, values in pairs.items()}
    # A fault that lasts three seconds inside a twelve-second run barely moves the
    # mean. The 90th percentile keeps short, severe episodes visible.
    p90 = {name: round(_percentile(values, 90), 4) for name, values in pairs.items()}
    votes = {
        "odom": p90["odom_vs_imu"] + p90["odom_vs_lidar"],
        "imu": p90["odom_vs_imu"] + p90["imu_vs_lidar"],
        "lidar": p90["odom_vs_lidar"] + p90["imu_vs_lidar"],
    }
    outlier = max(votes, key=votes.get)
    disagreement = max(p90.values())
    windows = [span for span in divergent_spans if span[1] - span[0] >= 10 * dt]
    return {
        "pairwise_mean_abs_diff": means,
        "pairwise_p90_abs_diff": p90,
        "outlier_sensor": outlier if disagreement > threshold and windows else None,
        "disagreement_score": round(disagreement, 4),
        "divergent_windows": windows,
    }


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round(pct / 100 * (len(ordered) - 1))))
    return ordered[index]


def _innovation(
    state: list[float], cov: list[list[float]], measurement: float, index: int, noise: float
) -> dict[str, float]:
    """Residual and normalized innovation squared against a frozen prediction."""
    residual = measurement - state[index]
    innovation_cov = cov[index][index] + noise
    return {
        "residual": residual,
        "innovation_cov": innovation_cov,
        "nis": residual * residual / innovation_cov,
    }


def run_fusion(samples: list[SensorSample], noise: dict[str, float] | None = None) -> dict[str, Any]:
    """Fuse a run and return per-sensor residual statistics."""
    noise = noise or dict(DEFAULT_R)
    ekf = EKF(dt=samples[1].t - samples[0].t if len(samples) > 1 else 0.05)
    residuals: dict[str, list[float]] = {"odom": [], "imu": [], "lidar": []}
    nis: dict[str, list[float]] = {"odom": [], "imu": [], "lidar": []}
    timeline: list[dict[str, Any]] = []

    for sample in samples:
        ekf.predict()
        # Innovations are measured against the *prediction*, before any sensor has
        # pulled the state. Updating first would let whichever sensor ran earliest
        # make every later sensor look like the outlier.
        predicted = list(ekf.state)
        predicted_cov = [row[:] for row in ekf.cov]
        stats = {
            "odom": _innovation(predicted, predicted_cov, sample.odom_velocity, 1, noise["odom"]),
            "imu": _innovation(predicted, predicted_cov, sample.imu_velocity, 1, noise["imu"]),
            "lidar": _innovation(predicted, predicted_cov, sample.lidar_position, 0, noise["lidar"]),
        }
        ekf.update(sample.odom_velocity, 1, noise["odom"])
        ekf.update(sample.imu_velocity, 1, noise["imu"])
        ekf.update(sample.lidar_position, 0, noise["lidar"])
        for sensor, value in stats.items():
            residuals[sensor].append(value["residual"])
            nis[sensor].append(value["nis"])
        timeline.append(
            {
                "t": round(sample.t, 2),
                "fused_v": round(ekf.state[1], 3),
                "odom_resid": round(stats["odom"]["residual"], 3),
                "imu_resid": round(stats["imu"]["residual"], 3),
                "lidar_resid": round(stats["lidar"]["residual"], 3),
            }
        )

    cross = _cross_checks(samples, dt=ekf.dt)

    summary = {
        sensor: {
            "mean_abs_residual": round(statistics.fmean(abs(r) for r in values), 4),
            "max_abs_residual": round(max(abs(r) for r in values), 4),
            "mean_nis": round(statistics.fmean(nis[sensor]), 3),
            "pct_nis_over_3": round(
                100 * sum(1 for v in nis[sensor] if v > 3.0) / len(nis[sensor]), 1
            ),
        }
        for sensor, values in residuals.items()
    }
    return {"per_sensor": summary, "cross_checks": cross, "timeline": timeline, "noise": noise}


def detect_disagreement(stats: dict[str, Any], nis_threshold: float = 3.0) -> list[Finding]:
    """Deterministic detection. Claude never gates a state estimate; this does."""
    findings: list[Finding] = []
    cross = stats["cross_checks"]
    outlier = cross["outlier_sensor"]
    if outlier:
        windows = cross["divergent_windows"]
        findings.append(
            Finding(
                severity="critical",
                title=f"{outlier} disagrees with the other two sensors",
                detail=(
                    f"Pairwise p90 absolute differences {cross['pairwise_p90_abs_diff']} put "
                    f"{outlier} furthest from consensus (score {cross['disagreement_score']}). "
                    + (f"Sustained divergence over {len(windows)} window(s): {windows}."
                       if windows else "No sustained window, so this may be noise.")
                ),
                source="rule",
                evidence=cross,
            )
        )
    for sensor, values in stats["per_sensor"].items():
        if values["mean_nis"] > nis_threshold:
            findings.append(
                Finding(
                    severity="warning",
                    title=f"{sensor} innovations exceed the chi-square gate",
                    detail=(
                        f"Mean NIS {values['mean_nis']} against a {nis_threshold} gate; "
                        f"{values['pct_nis_over_3']}% of updates fell outside 3 sigma. "
                        "A sensor the filter over-trusts can still show a small NIS, so read "
                        "this alongside the cross-sensor check."
                    ),
                    source="rule",
                    evidence={sensor: values},
                )
            )
    return findings


def analyze(
    samples: list[SensorSample] | None = None,
    *,
    client: ClaudeClient | None = None,
) -> AgentReport:
    samples = samples or generate_run()
    client = client or ClaudeClient()
    stats = run_fusion(samples)
    findings = detect_disagreement(stats)

    worst_window = sorted(stats["timeline"], key=lambda row: -abs(row["odom_resid"]))[:12]
    prompt = (
        "Cross-sensor agreement:\n"
        f"{json.dumps(stats['cross_checks'], indent=2)}\n\n"
        "Per-sensor residual statistics for the run:\n"
        f"{json.dumps(stats['per_sensor'], indent=2)}\n\n"
        f"Current measurement noise (R): {json.dumps(stats['noise'])}\n\n"
        "Worst 12 timesteps by odometry residual:\n"
        f"{json.dumps(worst_window, indent=2)}"
    )
    verdict = client.ask_json(
        SYSTEM,
        prompt,
        fallback={
            "diagnosis": "Odometry velocity disagrees with IMU and LiDAR during part of the run.",
            "likely_cause": "Wheel slip: encoders report motion the body never experienced.",
            "confidence": 0.7,
            "weight_adjustments": [
                {
                    "sensor": "odom",
                    "current_r": stats["noise"]["odom"],
                    "suggested_r": round(stats["noise"]["odom"] * 10, 4),
                    "reason": "Deweight encoders while slip persists.",
                }
            ],
            "actions": ["Gate odometry updates on an IMU-vs-encoder consistency check."],
        },
    )

    if verdict.get("diagnosis"):
        findings.append(
            Finding(
                severity="warning",
                title=verdict.get("likely_cause", "Model diagnosis"),
                detail=verdict["diagnosis"],
                source="claude",
                evidence={"confidence": verdict.get("confidence")},
            )
        )

    recommendations = list(verdict.get("actions") or [])
    for adjustment in verdict.get("weight_adjustments") or []:
        recommendations.append(
            f"Set R[{adjustment['sensor']}] {adjustment.get('current_r')} -> "
            f"{adjustment.get('suggested_r')}: {adjustment.get('reason', '')}".strip()
        )

    return AgentReport(
        agent="Sensor fusion anomaly agent",
        summary=verdict.get("diagnosis", "Fusion run analyzed."),
        findings=findings,
        metrics={
            **{f"{k}_mean_nis": v["mean_nis"] for k, v in stats["per_sensor"].items()},
            "outlier_sensor": stats["cross_checks"]["outlier_sensor"],
            "disagreement_score": stats["cross_checks"]["disagreement_score"],
        },
        recommendations=recommendations,
    )
