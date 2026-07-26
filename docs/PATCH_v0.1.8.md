# RAIDS-NIDS v0.1.8 nested-random and query-provenance patch

This cumulative patch retains the v0.1.7 guard-safe calibration protocol and
adds a paired random acquisition control:

```yaml
adaptation:
  selection: random_nested
  query_seed: 11
```

For each trigger window, one seeded permutation defines a complete query
ranking. A B50 selection is therefore an exact subset of B200 when all other
configuration fields match. The existing `random` behavior remains unchanged
for backward compatibility, and invalid strategy names now raise an error.

Every sequential record stores the ordered target-row indices selected in that
window and their SHA-256 hash. The run summary stores the combined ordered row
indices, combined hash, strategy, candidate multiplier, and integrity checks
for count agreement and row uniqueness. The query-provenance contract is
`1.1-exact-ordered-row-indices-and-sha256`.

Metric contract `1.3-acquisition-aware-selectable-trajectory` and drift
calibration contract `1.1-guard-safe-candidate-selection` are unchanged.
