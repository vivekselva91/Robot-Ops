"""A scripted E-stop incident: rogue thread starves the LiDAR driver."""

from __future__ import annotations

import random

from .buffer import IncidentBuffer, LogRecord

TRIGGER_T = 30.0


def build_incident(seed: int = 5) -> dict:
    rng = random.Random(seed)
    buffer = IncidentBuffer(window_s=30.0)

    for step in range(300):
        t = step * 0.1
        cpu_core3 = rng.gauss(30, 5)
        lidar_age_ms = rng.gauss(18, 3)
        if t > 22.0:  # localization thread runs away
            cpu_core3 = min(100.0, rng.gauss(96, 2))
            lidar_age_ms = rng.gauss(30 + (t - 22.0) * 9, 4)
        buffer.add_metrics(
            t,
            {
                "cpu_core0_pct": round(rng.gauss(35, 6), 1),
                "cpu_core3_pct": round(cpu_core3, 1),
                "mem_used_pct": round(rng.gauss(62, 3), 1),
                "lidar_msg_age_ms": round(max(0.0, lidar_age_ms), 1),
            },
        )
        if step % 10 == 0:
            buffer.add_snapshot(
                t,
                {
                    "base_velocity_mps": 0.0 if t > 29.8 else round(rng.gauss(0.9, 0.05), 2),
                    "nav_state": "E_STOP" if t > 29.8 else "TRACKING",
                    "localization_confidence": round(max(0.1, 0.95 - max(0.0, t - 22) * 0.08), 2),
                },
            )
        if t > 24.0 and step % 7 == 0:
            buffer.add_log(
                LogRecord(t, "ekf_localization", "WARN", "scan matching iteration overran budget")
            )
        if t > 27.0 and step % 5 == 0:
            buffer.add_log(
                LogRecord(t, "lidar_driver", "ERROR", "frame timeout: no scan within 50 ms")
            )

    buffer.add_log(LogRecord(29.6, "kernel", "WARN", "sched: rt throttling activated on cpu3"))
    buffer.add_log(LogRecord(29.8, "safety_monitor", "FATAL", "E-STOP asserted: lidar watchdog"))
    return buffer.freeze(trigger="E_STOP:lidar_watchdog", stamp=TRIGGER_T)
