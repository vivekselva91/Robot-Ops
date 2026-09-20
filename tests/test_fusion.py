from robotops.fusion.agent import detect_disagreement, run_fusion
from robotops.fusion.ekf import EKF
from robotops.fusion.sim import generate_run
from robotops.llm import ClaudeClient


def test_ekf_converges_on_constant_velocity():
    ekf = EKF(dt=0.05)
    for _ in range(200):
        ekf.predict()
        ekf.update(1.0, 1, 0.02)
    assert abs(ekf.state[1] - 1.0) < 0.05


def test_slip_window_identifies_odometry_as_the_outlier():
    stats = run_fusion(generate_run())
    cross = stats["cross_checks"]
    assert cross["outlier_sensor"] == "odom"
    assert cross["divergent_windows"], "expected a sustained divergence window during slip"


def test_detect_disagreement_is_quiet_on_clean_runs():
    clean = run_fusion(generate_run(slip_window=(999.0, 999.0)))
    assert clean["cross_checks"]["outlier_sensor"] is None
    assert all(f.severity != "critical" for f in detect_disagreement(clean))


def test_agent_runs_offline():
    from robotops.fusion.agent import analyze

    report = analyze(client=ClaudeClient(offline=True))
    assert report.agent.startswith("Sensor fusion")
    assert report.metrics
