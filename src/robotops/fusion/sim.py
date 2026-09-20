"""Synthetic drive data with an injectable wheel-slip window."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass
class SensorSample:
    t: float
    odom_velocity: float
    imu_velocity: float
    lidar_position: float
    true_velocity: float
    slipping: bool

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "t": round(self.t, 3),
            "odom_v": round(self.odom_velocity, 4),
            "imu_v": round(self.imu_velocity, 4),
            "lidar_p": round(self.lidar_position, 4),
            "slipping": self.slipping,
        }


def generate_run(
    duration: float = 12.0,
    dt: float = 0.05,
    slip_window: tuple[float, float] = (5.0, 8.0),
    seed: int = 7,
) -> list[SensorSample]:
    """Robot drives at 0.8 m/s. Inside the slip window the wheels spin freely:
    encoders keep reporting motion while the IMU and LiDAR see a stopped base."""
    rng = random.Random(seed)
    samples: list[SensorSample] = []
    position = 0.0
    steps = int(duration / dt)
    for i in range(steps):
        t = i * dt
        commanded = 0.8
        slipping = slip_window[0] <= t < slip_window[1]
        true_velocity = 0.0 if slipping else commanded
        position += true_velocity * dt

        odom_velocity = commanded + rng.gauss(0, 0.01)
        imu_velocity = true_velocity + rng.gauss(0, 0.03) + 0.002 * math.sin(t)
        lidar_position = position + rng.gauss(0, 0.02)
        samples.append(
            SensorSample(t, odom_velocity, imu_velocity, lidar_position, true_velocity, slipping)
        )
    return samples
