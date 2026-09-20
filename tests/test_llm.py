import pytest

from robotops.llm import _parse_json
from robotops.schemas import AgentReport, Finding


def test_parse_json_strips_fences():
    assert _parse_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert _parse_json('Here you go: {"a": 2} thanks') == {"a": 2}
    with pytest.raises(ValueError):
        _parse_json("no object here")


def test_worst_severity():
    report = AgentReport(agent="x", summary="y")
    assert report.worst_severity == "info"
    report.findings.append(Finding("warning", "t", "d", "rule"))
    report.findings.append(Finding("critical", "t", "d", "rule"))
    assert report.worst_severity == "critical"
