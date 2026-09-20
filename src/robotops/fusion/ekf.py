"""A small constant-velocity EKF over a 1-D drive axis.

State is [position, velocity]. Wheel odometry and IMU-integrated velocity are
velocity measurements; LiDAR scan-matching gives position. The filter is here so
the anomaly agent has real residuals to reason about, not so it competes with
robot_localization.
"""

from __future__ import annotations

from dataclasses import dataclass, field


def _mat_add(a, b):
    return [[a[i][j] + b[i][j] for j in range(len(a[0]))] for i in range(len(a))]


@dataclass
class EKF:
    dt: float = 0.05
    q_pos: float = 1e-4
    q_vel: float = 1e-3
    state: list[float] = field(default_factory=lambda: [0.0, 0.0])
    cov: list[list[float]] = field(default_factory=lambda: [[0.1, 0.0], [0.0, 0.1]])

    def predict(self) -> None:
        p, v = self.state
        self.state = [p + v * self.dt, v]
        f = [[1.0, self.dt], [0.0, 1.0]]
        fp = [
            [f[0][0] * self.cov[0][0] + f[0][1] * self.cov[1][0],
             f[0][0] * self.cov[0][1] + f[0][1] * self.cov[1][1]],
            [f[1][0] * self.cov[0][0] + f[1][1] * self.cov[1][0],
             f[1][0] * self.cov[0][1] + f[1][1] * self.cov[1][1]],
        ]
        fpft = [
            [fp[0][0] * f[0][0] + fp[0][1] * f[0][1], fp[0][0] * f[1][0] + fp[0][1] * f[1][1]],
            [fp[1][0] * f[0][0] + fp[1][1] * f[0][1], fp[1][0] * f[1][0] + fp[1][1] * f[1][1]],
        ]
        self.cov = _mat_add(fpft, [[self.q_pos, 0.0], [0.0, self.q_vel]])

    def update(self, measurement: float, index: int, noise: float) -> dict[str, float]:
        """Scalar update on one state component. Returns residual diagnostics."""
        residual = measurement - self.state[index]
        innovation_cov = self.cov[index][index] + noise
        gain = [self.cov[0][index] / innovation_cov, self.cov[1][index] / innovation_cov]
        self.state = [self.state[0] + gain[0] * residual, self.state[1] + gain[1] * residual]
        row = list(self.cov[index])
        for i in range(2):
            for j in range(2):
                self.cov[i][j] -= gain[i] * row[j]
        nis = residual * residual / innovation_cov
        return {"residual": residual, "innovation_cov": innovation_cov, "nis": nis}
