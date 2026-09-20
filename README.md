# robot-ops-copilot

Five Claude-powered reliability agents for robotics fleets: sensor-fusion sanity checks, ROS 2 uptime tracking, edge-to-cloud latency profiling, automated root cause analysis, and predictive maintenance for actuators.

Every agent runs offline against a built-in synthetic scenario, so you can clone the repo and see all five working before you point them at a robot or spend a token.

```bash
git clone https://github.com/<you>/robot-ops-copilot.git
cd robot-ops-copilot
pip install -e ".[dev]"
robotops fusion --offline     # no API key needed
```

## The design rule

Deterministic code decides. Claude explains.

Each agent splits into two halves. Plain Python owns detection: filters, thresholds, percentiles, trend fits. It is testable, fast, and never hallucinates. Claude reads the resulting summary and supplies what statistics cannot — the physical cause, the cross-signal correlation, the recommended fix in engineering language.

This is not an aesthetic preference. A language model has no place inside a state estimator's update loop or a watchdog's decision path, and anything safety-critical must hold when the API is unreachable. So every agent produces its findings with or without a model, and the `source` field on each finding records which half produced it: `rule` or `claude`.

## The five agents

| Command | What it watches | Deterministic half | Claude's half |
|---|---|---|---|
| `robotops fusion` | IMU, wheel odometry, LiDAR | EKF innovations, cross-sensor p90 voting | Names the physical cause, proposes R adjustments |
| `robotops diagnostics` | ROS 2 `/diagnostics` | Uptime, MTBF, stale heartbeats, CPU peaks | Correlates failures across nodes |
| `robotops latency` | Teleop round trips | Per-stage p50/p95/p99, jitter, budget breaches | Attributes the bottleneck to a cause |
| `robotops rca` | E-stops and crashes | 30 s rolling buffer, peak extraction | Writes the RCA: proximate vs root cause |
| `robotops maintenance` | Motor telemetry | Current-per-velocity drift vs own baseline | Identifies the failing component |

### 1. Sensor fusion anomaly agent

Runs a constant-velocity EKF over wheel odometry, IMU and LiDAR, then looks for disagreement.

The interesting part is that innovation gating alone does not catch wheel slip. Odometry usually has the tightest `R`, so during slip the filter follows the encoders, which keeps the odometry residual small and makes the honest sensors look wrong. The agent therefore compares sensors against each other and takes a majority vote: the sensor furthest from consensus is the outlier, not the one with the largest residual against a state it already corrupted.

```
[CRIT] odom disagrees with the other two sensors (rule)
    Pairwise p90 absolute differences {'odom_vs_imu': 0.7986, 'odom_vs_lidar': 0.8016,
    'imu_vs_lidar': 0.1388} put odom furthest from consensus (score 0.8016).
    Sustained divergence over 1 window(s): [(5.0, 8.0)].
```

The synthetic run injects slip from t=5.0 s to t=8.0 s. The detector recovers that window exactly.

### 2. ROS 2 diagnostic and uptime agent

Consumes `diagnostic_msgs/DiagnosticArray` and computes per-node uptime, failure episodes, MTBF and resource peaks, then alerts through Slack or Discord.

Claude's contribution is correlation. In the bundled scenario the camera driver goes stale twice, and a naive dashboard blames the camera. The agent notices the second dropout coincides with the localization node saturating a core, and reports the camera as a victim of CPU starvation rather than a faulty driver.

### 3. Edge-to-cloud latency profiler

Records per-stage spans across acquisition, serialization, uplink, cloud inference, downlink and actuation, then separates network jitter from cold starts from serialization overhead. A stage with a low p50 and a high p95 is jitter; a stage with periodic multi-second spikes is a cold shard. Those need opposite fixes, which is why the distinction matters more than the raw number.

### 4. Automated RCA bot

Keeps a rolling 30-second buffer of logs, metrics and state snapshots. On an E-stop it freezes the window and asks Claude for a written RCA that separates the proximate cause (what asserted the fault) from the root cause (what made it inevitable), names the layer, and lists what evidence was missing.

The bundled incident walks back from a LiDAR watchdog E-stop to a localization thread saturating core 3 — the watchdog is the symptom, the scheduler is the cause.

### 5. Predictive maintenance copilot

Tracks current draw normalized by actual velocity against each joint's own early-life baseline. Raw current tells you how hard a joint is working; current per unit velocity tells you how much of that work is going into friction. The bundled telemetry has one joint gaining 21% friction over 40 hours while two others stay flat, and the agent flags only the worn one.

## Using it on a real robot

Nothing in the analysis layer imports `rclpy`. The bridge in `src/robotops/ros2/bridge.py` converts real `DiagnosticArray` messages into the same records the simulators produce:

```python
from robotops.ros2.bridge import spin_diagnostics
from robotops.diagnostics.agent import analyze

buffer = []
spin_diagnostics(on_batch=buffer.extend)   # requires a sourced ROS 2 install
report = analyze(buffer)
```

The same substitution works for the other four: pass your own samples to `analyze()` instead of letting it call the generator.

## Configuration

```bash
cp .env.example .env
```

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | Enables live Claude calls. Without it, agents use deterministic fallbacks. |
| `ROBOTOPS_MODEL` | Defaults to `claude-sonnet-5`. |
| `ROBOTOPS_MAX_TOKENS` | Response cap, defaults to 2000. |
| `ROBOTOPS_SLACK_WEBHOOK` / `ROBOTOPS_DISCORD_WEBHOOK` | Alert delivery for `--alert`. Unset prints to stdout. |

## CLI

```bash
robotops <agent> [--offline] [--json] [--markdown PATH] [--alert]
```

Exit code is 2 when any finding is critical, which makes the agents usable as CI or cron gates.

## Development

```bash
make dev     # install with test and llm extras
make test    # pytest
make lint    # ruff
make demo    # run all five agents
```

Tests cover the deterministic half only, and run without an API key. That is deliberate: the parts that make decisions are the parts that need to be provably correct.

## Repository layout

```
src/robotops/
  llm.py            Claude wrapper: JSON replies, retries, offline stub
  schemas.py        Finding and AgentReport
  report.py         console and markdown rendering
  cli.py            entry point
  fusion/           ekf.py  sim.py  agent.py
  diagnostics/      model.py  sim.py  alerts.py  agent.py
  latency/          trace.py  sim.py  agent.py
  rca/              buffer.py  sim.py  agent.py
  maintenance/      features.py  sim.py  agent.py
  ros2/             bridge.py (optional, lazy rclpy import)
```

## Limitations

The simulators are illustrative, not validated models of any real platform. The EKF is a teaching-scale 1-D filter, not a replacement for `robot_localization`. Remaining-life extrapolation in the maintenance agent is linear and will be wrong for wear that accelerates. Treat every Claude-sourced finding as a hypothesis to check, not a conclusion to act on unreviewed.

## License

MIT. See [LICENSE](LICENSE).
