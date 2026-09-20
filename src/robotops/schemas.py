"""Shared record types. Plain dataclasses keep the package dependency-free."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Finding:
    """One thing an agent concluded, deterministic or model-generated."""

    severity: str  # info | warning | critical
    title: str
    detail: str
    source: str  # "rule" or "claude"
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentReport:
    agent: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "summary": self.summary,
            "findings": [f.to_dict() for f in self.findings],
            "metrics": self.metrics,
            "recommendations": self.recommendations,
        }

    @property
    def worst_severity(self) -> str:
        order = {"info": 0, "warning": 1, "critical": 2}
        return max((f.severity for f in self.findings), key=lambda s: order.get(s, 0), default="info")
