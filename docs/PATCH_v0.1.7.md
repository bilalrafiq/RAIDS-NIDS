# RAIDS-NIDS v0.1.7 guard-safe calibration patch

This cumulative patch retains the v0.1.6 acquisition-aware metrics and event
builder, and automates the pre-event-only guard rule motivated by the first
NF-CICIDS2018-v3 DDoS diagnostic.

## Configuration

```yaml
adaptation:
  drift:
    reference_mode: target_warmup
    reference_start_window: 0
    reference_end_window: 10
    calibration_start_window: 10
    calibration_end_window: 30
    guard_start_window: 30
    guard_end_window: 40
    monitoring_start_window: 40
    mad_multiplier_candidates: [3, 4, 5, 6]
    consecutive_windows: 2
    min_windows_between: 3
    one_shot: true
    unknown_rate_threshold: 1.1
```

The runner scores every candidate on the unlabelled guard only, selects the
smallest multiplier producing zero persistent triggers, then begins deployment
monitoring after the guard. Candidate selection never reads target labels. If
none of the prespecified candidates is safe, the run raises an error rather
than extending the search using post-change outcomes.

`drift_calibration.json` now records the candidate set, every candidate's guard
flags and trigger windows, the selected multiplier and threshold, guard shift
scores, guard unknown rates, segment boundaries, and label-use assertions. The
drift-calibration contract identifier is
`1.1-guard-safe-candidate-selection`; the metric contract remains
`1.3-acquisition-aware-selectable-trajectory`.

The original fixed-`mad_multiplier` configuration remains backward compatible
under drift-calibration contract `1.0-fixed-mad`.
