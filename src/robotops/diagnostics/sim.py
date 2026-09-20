"""Synthetic diagnostic stream: a camera driver that drops out twice."""

from __future__ import annotations

import random

from .model import ERROR, OK, STALE, WARN, DiagnosticStatus

NODES = ["camera_driver", "lidar_driver", "ekf_localization", "nav2_controller", "motor_bridge"]


def generate_stream(duration: float = 600.0, period: float = 1.0, seed: int = 11):
    rng = random.Random(seed)
    statuses: list[DiagnosticStatus] = []
    for step in range(int(duration / period)):
        t = step * period
        for node in NODES:
            level, message = OK, "alive"
            if node == "camera_driver" and (120 <= t < 150 or 400 <= t < 470):
                level, message = STALE, "no frames received"
            elif node == "nav2_controller" and 405 <= t < 425:
                level, message = WARN, "controller period overrun"
            elif node == "motor_bridge" and 300 <= t < 302:
                level, message = ERROR, "CAN bus write timeout"
            cpu = rng.gauss(18, 4)
            if node == "ekf_localization" and 395 <= t < 430:
                cpu = rng.gauss(92, 3)
            statuses.append(
                DiagnosticStatus(
                    stamp=t,
                    name=node,
                    level=level,
                    message=message,
                    values={"cpu_pct": max(0.0, cpu), "mem_mb": rng.gauss(180, 20)},
                )
            )
    return statuses
