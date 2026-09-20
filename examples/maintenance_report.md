# Predictive maintenance copilot

One joint shows friction growth consistent with gearbox wear.

## Metrics

- **joint_1_shoulder_drift_pct**: -0.0
- **joint_2_elbow_drift_pct**: 21.6
- **joint_3_wrist_drift_pct**: 0.1

## Findings

### CRITICAL: joint_2_elbow drawing more current for the same velocity
Current per unit velocity rose 21.6% against its own baseline (2.429 -> 2.953); peak temperature 56.4 C. Linear extrapolation reaches the wear limit in about 24.8 operating hours.

```json
{
  "samples": 72000,
  "mean_current_a": 1.863,
  "max_temperature_c": 56.4,
  "temperature_slope_per_sample": 0.00016,
  "current_per_velocity_baseline": 2.429,
  "current_per_velocity_recent": 2.953,
  "efficiency_drift_pct": 21.6,
  "mean_tracking_error": 0.0043,
  "current_slope_per_sample": 1e-05
}
```

### CRITICAL: joint_2_elbow: gearbox or bearing
Efficiency drift 21.6% with temperature slope 0.00016.

```json
{
  "hours_remaining": 24.8
}
```

## Recommended actions

1. Schedule inspection of the flagged joint at the next maintenance window.
