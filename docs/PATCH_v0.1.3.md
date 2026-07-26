# RAIDS-NIDS v0.1.3 metric patch

This patch separates online decision windows from resilience-evaluation blocks.

## Configuration contract

```yaml
stream:
  window_size: 500
  true_change_window: 40

metrics:
  evaluation_window_size: 5000
  recovery_fraction: 0.95
  recovery_patience_evaluation_blocks: 3
  normal_labels: [Benign]
  minimum_evaluation_known_classes: 6
  minimum_evaluation_rows_per_known_class: 5
  minimum_evaluation_non_normal_rows: 100
```

`metrics.evaluation_window_size` must be an integer multiple of
`stream.window_size`. The declared change row must fall on an evaluation-block
boundary.

## Outputs

- `windows.csv` retains the 500-row prequential detection and adaptation trace.
- `evaluation_windows.csv` contains the 5,000-row support-audited metric trace.
- `summary.json` uses support-eligible evaluation blocks for the primary
  normalized recovery area and sustained recovery time.
- The former two-window stream result remains available as
  `stream_first_passage_recovery_time_windows`, but it is diagnostic rather than
  primary.

The metric contract identifier is
`1.2-decoupled-support-aware-evaluation`.
