from robotops.diagnostics.model import OK, STALE, DiagnosticStatus, aggregate, stale_nodes
from robotops.diagnostics.sim import generate_stream
from robotops.llm import ClaudeClient


def test_uptime_and_mtbf():
    statuses = [DiagnosticStatus(stamp=float(t), name="cam", level=OK) for t in range(10)]
    statuses += [DiagnosticStatus(stamp=10.0, name="cam", level=STALE)]
    statuses += [DiagnosticStatus(stamp=float(t), name="cam", level=OK) for t in range(11, 20)]
    statuses += [DiagnosticStatus(stamp=20.0, name="cam", level=STALE)]
    health = aggregate(statuses)["cam"]
    assert health.uptime_pct < 100.0
    assert health.mtbf_seconds == 10.0


def test_stale_detection():
    statuses = [DiagnosticStatus(stamp=0.0, name="lidar", level=OK)]
    assert stale_nodes(statuses, now=30.0, timeout=5.0) == ["lidar"]
    assert stale_nodes(statuses, now=2.0, timeout=5.0) == []


def test_camera_dropout_is_flagged():
    from robotops.diagnostics.agent import analyze

    report = analyze(generate_stream(), client=ClaudeClient(offline=True))
    titles = " ".join(f.title for f in report.findings)
    assert "camera_driver" in titles
    assert report.worst_severity == "critical"
