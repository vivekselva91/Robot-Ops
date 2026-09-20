from robotops.llm import ClaudeClient
from robotops.maintenance.agent import analyze
from robotops.maintenance.features import linear_trend
from robotops.maintenance.sim import generate_telemetry


def test_linear_trend_sign():
    assert linear_trend([1, 2, 3, 4]) > 0
    assert linear_trend([4, 3, 2, 1]) < 0
    assert abs(linear_trend([2, 2, 2, 2])) < 1e-9


def test_worn_joint_is_flagged_and_healthy_joints_are_not():
    report = analyze(generate_telemetry(hours=20), client=ClaudeClient(offline=True))
    flagged = " ".join(f.title for f in report.findings)
    assert "joint_2_elbow" in flagged
    assert "joint_1_shoulder" not in flagged
