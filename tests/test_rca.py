from robotops.llm import ClaudeClient
from robotops.rca.buffer import IncidentBuffer, LogRecord
from robotops.rca.sim import build_incident


def test_buffer_evicts_outside_window():
    buffer = IncidentBuffer(window_s=5.0)
    for t in range(20):
        buffer.add_log(LogRecord(float(t), "node", "INFO", "tick"))
    stamps = [record.stamp for record in buffer.logs]
    assert max(stamps) - min(stamps) <= 5.0


def test_incident_bundle_has_fatal_log():
    bundle = build_incident()
    assert bundle["counts"]["errors"] > 0
    assert any(log["lvl"] == "FATAL" for log in bundle["logs"])


def test_preprocess_finds_cpu_peak():
    from robotops.rca.agent import analyze, preprocess

    bundle = build_incident()
    derived = preprocess(bundle)
    assert derived["peaks"]["cpu_core3_pct"] > 85
    report = analyze(bundle, client=ClaudeClient(offline=True))
    assert report.worst_severity == "critical"
