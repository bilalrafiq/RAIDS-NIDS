# RAIDS-NIDS v0.1.4 drift-gate patch

This patch adds an unlabelled target-warm-up shift detector.

```yaml
adaptation:
  drift:
    reference_mode: target_warmup
    reference_start_window: 0
    reference_end_window: 10
    calibration_start_window: 10
    calibration_end_window: 30
    monitoring_start_window: 30
    mad_multiplier: 3
    consecutive_windows: 2
    min_windows_between: 3
    one_shot: true
    unknown_rate_threshold: 1.1
```

The threshold is the calibration median plus the configured multiplier times
the scaled MAD. No target labels enter reference construction or calibration.
Monitoring begins only after calibration. Consecutive exceedances are required,
and `one_shot: true` latches the detector after the first event so a persistent
shift is not counted repeatedly.

Every run saves `drift_calibration.json`. `summary.json` includes the frozen
threshold, trigger windows, monitored pre-change denominator, false-trigger
count, label-budget utilization, and realized target-label fraction.
