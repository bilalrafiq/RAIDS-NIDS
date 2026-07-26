# RAIDS-NIDS v0.1.5 anchored-adaptation patch

This cumulative patch adds an experimental stability-plasticity safeguard:

```yaml
method:
  update_rule: source_anchored
  minimum_target_samples_per_class: 5
  anchor_reliability_tau: 25
  anchor_max_alpha: 0.05

adaptation:
  label_budget_mode: absolute
  label_budget_total: 50
  max_queries_per_event: 50
  query_seed: 11
```

For each class, target embeddings accumulate until minimum support is reached.
Known-class prototypes remain anchored to immutable source prototypes. Target
influence is reliability-shrunk and capped by `anchor_max_alpha`. Novel classes
can still be created after minimum support.

Run summaries now record the exact queried class counts, independent query seed,
absolute-budget utilization, and per-class update coefficients. The original
`replay` update remains unchanged as a baseline.
