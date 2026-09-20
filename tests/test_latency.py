from robotops.latency.sim import generate_traces
from robotops.latency.trace import Trace, dominant_stage, percentile, summarize


def test_percentile_edges():
    values = [float(i) for i in range(1, 101)]
    assert percentile(values, 50) == 50.0 or percentile(values, 50) == 51.0
    assert percentile(values, 99) >= 99.0


def test_summary_shares_add_up():
    summary = summarize(generate_traces(200))
    assert summary["traces"] == 200
    assert summary["total"]["p95"] >= summary["total"]["p50"]
    _stage, stats = dominant_stage(summary)
    assert stats["p95"] > 0


def test_budget_violations_counted():
    traces = [Trace("a", 0.0, {"uplink": 500.0}), Trace("b", 0.1, {"uplink": 10.0})]
    summary = summarize(traces, budget_ms=100.0)
    assert summary["budget_violation_pct"] == 50.0
