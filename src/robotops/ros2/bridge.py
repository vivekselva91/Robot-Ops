"""Optional ROS 2 bridge.

Importing rclpy is deliberately lazy: the whole package runs, tests and demos
without ROS installed. On a real robot, `ros2_available()` returns True and the
subscriber nodes below feed the same agents that the synthetic generators feed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..diagnostics.model import DiagnosticStatus


def ros2_available() -> bool:
    try:
        import rclpy  # noqa: F401
    except ImportError:
        return False
    return True


def convert_diagnostic_array(msg: Any) -> list[DiagnosticStatus]:
    """diagnostic_msgs/DiagnosticArray -> our records."""
    stamp = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
    out = []
    for status in msg.status:
        values = {kv.key: kv.value for kv in status.values}
        for key in ("cpu_pct", "mem_mb"):
            if key in values:
                try:
                    values[key] = float(values[key])
                except ValueError:
                    values.pop(key)
        out.append(
            DiagnosticStatus(
                stamp=stamp,
                name=status.name,
                level=int.from_bytes(status.level, "big")
                if isinstance(status.level, bytes)
                else int(status.level),
                message=status.message,
                values=values,
            )
        )
    return out


def spin_diagnostics(on_batch: Callable[[list[DiagnosticStatus]], None], topic: str = "/diagnostics"):
    """Subscribe to /diagnostics and hand batches to a callback. Requires rclpy."""
    if not ros2_available():
        raise RuntimeError("rclpy not importable: source your ROS 2 setup first")

    import rclpy
    from diagnostic_msgs.msg import DiagnosticArray
    from rclpy.node import Node

    class DiagnosticsListener(Node):
        def __init__(self) -> None:
            super().__init__("robotops_diagnostics_listener")
            self.create_subscription(DiagnosticArray, topic, self._callback, 10)

        def _callback(self, msg: DiagnosticArray) -> None:
            on_batch(convert_diagnostic_array(msg))

    rclpy.init()
    node = DiagnosticsListener()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()
