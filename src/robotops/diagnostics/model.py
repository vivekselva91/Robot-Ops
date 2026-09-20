"""ROS 2 diagnostic records and uptime math.

Mirrors diagnostic_msgs/DiagnosticArray without importing ROS, so the analysis
runs on a laptop against a rosbag export as easily as on the robot.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Any

OK, WARN, ERROR, STALE = 0, 1, 2, 3
LEVEL_NAMES = {OK: "OK", WARN: "WARN", ERROR: "ERROR", STALE: "STALE"}


@dataclass
class DiagnosticStatus:
    stamp: float
    name: str
    level: int
    message: str = ""
    values: dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeHealth:
    name: str
    samples: int = 0
    ok_samples: int = 0
    transitions: list[tuple[float, int, int]] = field(default_factory=list)
    failures: list[float] = field(default_factory=list)
    last_level: int | None = None
    cpu: list[float] = field(default_factory=list)
    memory: list[float] = field(default_factory=list)

    @property
    def uptime_pct(self) -> float:
        return round(100.0 * self.ok_samples / self.samples, 2) if self.samples else 0.0

    @property
    def mtbf_seconds(self) -> float | None:
        """Mean time between the starts of consecutive failure episodes."""
        if len(self.failures) < 2:
            return None
        gaps = [b - a for a, b in zip(self.failures, self.failures[1:])]
        return round(statistics.fmean(gaps), 1)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node": self.name,
            "uptime_pct": self.uptime_pct,
            "failure_episodes": len(self.failures),
            "mtbf_s": self.mtbf_seconds,
            "mean_cpu_pct": round(statistics.fmean(self.cpu), 1) if self.cpu else None,
            "mean_mem_mb": round(statistics.fmean(self.memory), 1) if self.memory else None,
            "last_level": LEVEL_NAMES.get(self.last_level or OK),
        }


def aggregate(statuses: list[DiagnosticStatus]) -> dict[str, NodeHealth]:
    health: dict[str, NodeHealth] = {}
    for status in sorted(statuses, key=lambda s: s.stamp):
        node = health.setdefault(status.name, NodeHealth(name=status.name))
        node.samples += 1
        if status.level == OK:
            node.ok_samples += 1
        if node.last_level is not None and status.level != node.last_level:
            node.transitions.append((status.stamp, node.last_level, status.level))
            if node.last_level == OK and status.level in (ERROR, STALE):
                node.failures.append(status.stamp)
        elif node.last_level is None and status.level in (ERROR, STALE):
            node.failures.append(status.stamp)
        node.last_level = status.level
        if "cpu_pct" in status.values:
            node.cpu.append(float(status.values["cpu_pct"]))
        if "mem_mb" in status.values:
            node.memory.append(float(status.values["mem_mb"]))
    return health


def stale_nodes(statuses: list[DiagnosticStatus], now: float, timeout: float = 5.0) -> list[str]:
    """Nodes whose last heartbeat is older than the timeout."""
    last_seen: dict[str, float] = {}
    for status in statuses:
        last_seen[status.name] = max(last_seen.get(status.name, 0.0), status.stamp)
    return sorted(name for name, seen in last_seen.items() if now - seen > timeout)
