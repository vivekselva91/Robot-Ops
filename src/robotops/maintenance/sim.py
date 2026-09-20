"""Synthetic motor telemetry: one healthy joint, one with a failing gearbox."""

from __future__ import annotations

import random

from .features import MotorSample

JOINTS = ["joint_1_shoulder", "joint_2_elbow", "joint_3_wrist"]


def generate_telemetry(hours: float = 40.0, sample_hz: float = 0.5, seed: int = 13):
    """joint_2_elbow slowly gains friction: more current for the same velocity."""
    rng = random.Random(seed)
    samples: list[MotorSample] = []
    total = int(hours * 3600 * sample_hz)
    for step in range(total):
        t = step / sample_hz
        progress = step / total
        for joint in JOINTS:
            commanded = 0.6 + 0.2 * rng.random()
            friction = 1.0
            temp_base = 42.0
            if joint == "joint_2_elbow":
                friction = 1.0 + 0.26 * progress**1.4
                temp_base = 42.0 + 11.0 * progress**1.4
            actual = commanded * (1.0 - 0.02 * (friction - 1.0)) + rng.gauss(0, 0.005)
            samples.append(
                MotorSample(
                    t=t,
                    joint=joint,
                    current_a=round(2.4 * commanded * friction + rng.gauss(0, 0.05), 4),
                    temperature_c=round(temp_base + rng.gauss(0, 1.1), 2),
                    voltage_v=round(47.8 + rng.gauss(0, 0.2), 2),
                    commanded_velocity=round(commanded, 4),
                    actual_velocity=round(actual, 4),
                )
            )
    return samples
