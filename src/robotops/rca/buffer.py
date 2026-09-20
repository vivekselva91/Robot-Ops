"""A rolling incident buffer.

Everything worth reading after a failure has already scrolled past by the time
the failure happens, so the buffer keeps the last N seconds of logs, metrics and
sensor snapshots in memory and freezes them when a trigger fires.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LogRecord:
    stamp: float
    source: str  # node, kernel, middleware
    level: str  # DEBUG | INFO | WARN | ERROR | FATAL
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "t": round(self.stamp, 3),
            "src": self.source,
            "lvl": self.level,
            "msg": self.message,
        }


@dataclass
class IncidentBuffer:
    window_s: float = 30.0
    logs: deque[LogRecord] = field(default_factory=deque)
    metrics: deque[tuple[float, dict[str, Any]]] = field(default_factory=deque)
    snapshots: deque[tuple[float, dict[str, Any]]] = field(default_factory=deque)

    def add_log(self, record: LogRecord) -> None:
        self.logs.append(record)
        self._trim(self.logs, record.stamp, key=lambda r: r.stamp)

    def add_metrics(self, stamp: float, values: dict[str, Any]) -> None:
        self.metrics.append((stamp, values))
        self._trim(self.metrics, stamp, key=lambda item: item[0])

    def add_snapshot(self, stamp: float, state: dict[str, Any]) -> None:
        self.snapshots.append((stamp, state))
        self._trim(self.snapshots, stamp, key=lambda item: item[0])

    def _trim(self, container: deque, now: float, key) -> None:
        while container and now - key(container[0]) > self.window_s:
            container.popleft()

    def freeze(self, trigger: str, stamp: float | None = None) -> dict[str, Any]:
        """Capture the current window as an immutable incident bundle."""
        stamp = stamp if stamp is not None else time.time()
        return {
            "trigger": trigger,
            "triggered_at": round(stamp, 3),
            "window_s": self.window_s,
            "logs": [record.to_dict() for record in self.logs],
            "metrics": [{"t": round(t, 3), **values} for t, values in self.metrics],
            "snapshots": [{"t": round(t, 3), **state} for t, state in self.snapshots],
            "counts": {
                "logs": len(self.logs),
                "errors": sum(1 for r in self.logs if r.level in ("ERROR", "FATAL")),
            },
        }
