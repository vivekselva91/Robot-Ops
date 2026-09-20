"""Wear features from motor telemetry.

The useful signal is not raw current, it is current normalized by the work the
joint is actually doing. A joint drawing more amps for the same velocity under
the same load is a joint whose friction is rising.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Any


@dataclass
class MotorSample:
    t: float
    joint: str
    current_a: float
    temperature_c: float
    voltage_v: float
    commanded_velocity: float
    actual_velocity: float


def linear_trend(values: list[float]) -> float:
    """Least-squares slope per sample index. Positive means rising."""
    n = len(values)
    if n < 2:
        return 0.0
    mean_x = (n - 1) / 2
    mean_y = statistics.fmean(values)
    numerator = sum((i - mean_x) * (v - mean_y) for i, v in enumerate(values))
    denominator = sum((i - mean_x) ** 2 for i in range(n))
    return numerator / denominator if denominator else 0.0


def joint_features(samples: list[MotorSample], baseline_fraction: float = 0.2) -> dict[str, Any]:
    currents = [s.current_a for s in samples]
    temps = [s.temperature_c for s in samples]
    efficiency = [
        s.current_a / max(abs(s.actual_velocity), 1e-3) for s in samples
    ]
    tracking_error = [abs(s.commanded_velocity - s.actual_velocity) for s in samples]

    split = max(2, int(len(samples) * baseline_fraction))
    baseline = statistics.fmean(efficiency[:split])
    recent = statistics.fmean(efficiency[-split:])
    drift_pct = 100 * (recent - baseline) / baseline if baseline else 0.0

    return {
        "samples": len(samples),
        "mean_current_a": round(statistics.fmean(currents), 3),
        "max_temperature_c": round(max(temps), 1),
        "temperature_slope_per_sample": round(linear_trend(temps), 5),
        "current_per_velocity_baseline": round(baseline, 3),
        "current_per_velocity_recent": round(recent, 3),
        "efficiency_drift_pct": round(drift_pct, 1),
        "mean_tracking_error": round(statistics.fmean(tracking_error), 4),
        "current_slope_per_sample": round(linear_trend(currents), 5),
    }


def hours_to_threshold(features: dict[str, Any], sample_hz: float, limit_pct: float = 35.0):
    """Extrapolate the efficiency drift to a failure threshold. Rough by design."""
    drift = features["efficiency_drift_pct"]
    if drift <= 0:
        return None
    samples_elapsed = features["samples"]
    rate_per_sample = drift / samples_elapsed
    if rate_per_sample <= 0:
        return None
    remaining = (limit_pct - drift) / rate_per_sample
    return round(max(0.0, remaining) / sample_hz / 3600.0, 1)
