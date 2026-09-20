"""Synthetic teleop traces with network jitter and periodic inference stalls."""

from __future__ import annotations

import random

from .trace import Trace

BASELINE_MS = {
    "sensor_acquire": 4.0,
    "serialize": 6.0,
    "uplink": 22.0,
    "cloud_inference": 35.0,
    "downlink": 18.0,
    "deserialize": 3.0,
    "actuate": 5.0,
}


def generate_traces(count: int = 500, seed: int = 3) -> list[Trace]:
    rng = random.Random(seed)
    traces: list[Trace] = []
    for i in range(count):
        stages = {name: max(0.1, rng.gauss(mean, mean * 0.12)) for name, mean in BASELINE_MS.items()}
        # Every ~40th trace hits a cold model shard.
        if i % 40 == 0:
            stages["cloud_inference"] *= rng.uniform(3.5, 6.0)
        # A burst of uplink jitter in the middle of the run.
        if 200 <= i < 260:
            stages["uplink"] += rng.expovariate(1 / 45.0)
        traces.append(
            Trace(
                trace_id=f"tr-{i:04d}",
                t_start=i * 0.05,
                stages={k: round(v, 2) for k, v in stages.items()},
            )
        )
    return traces
