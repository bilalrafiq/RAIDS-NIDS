# RAIDS-NIDS v0.1.11 scoring patch

Version 0.1.11 preserves all v0.18, v0.19, and v0.20 evidence. It adds the
separately numbered v0.21 source-anchored shift-score amendment.

The v0.20 seed-11 diagnostic showed that very small target-reference variance
allowed `DNS_TTL_ANSWER` and `DNS_QUERY_TYPE` to contribute nearly 100% of
several shift scores. The historical `+1e-6` term protected division but did
not provide a meaningful scale floor.

The corrected denominator for dimension `j` is:

```text
max(target_reference_std_j, source_training_std_j, 1e-6)
```

No target post-change row or target label enters this denominator. The model,
event artifacts, stream windows, robust trace normalization, detector
candidates, and guard-selection rules remain unchanged.

Seed 11 is reserved for development and excluded from the primary aggregate.
The corrected evaluation uses seeds 22 through 121 as declared in the v0.21
protocol.
