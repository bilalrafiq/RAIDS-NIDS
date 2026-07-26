# RAIDS-NIDS v0.21 validation report

**Validation date:** 24 July 2026  
**Package version:** 0.1.11  
**Purpose:** engineering validation of the source-anchored shift-score
amendment before any v0.21 real-data outcome is opened

## Evidence boundary

The v0.20 event-construction evidence remains valid and unchanged:

- DoS failed construction.
- Exploits constructed and passed its event-integrity checks.
- Reconnaissance constructed and passed its event-integrity checks.

The user then ran the prespecified v0.20 seed-11 diagnostic. Its score audit
showed that `DNS_TTL_ANSWER` or `DNS_QUERY_TYPE` contributed approximately
99.98% to 100% of multiple large shift scores. The v0.20 seed-11 guard results
are retained as diagnostic evidence and excluded from inference.

No v0.21 score trace, detector trigger, delay, or aggregate result was
generated during package validation.

## Frozen correction

Protocol:

```text
configs/protocols/v021_source_anchored_score_amendment.yaml
```

SHA-256:

```text
8bf4ae3fd53ae31990f5ecac1e431364000004a6c81a7d082c7b740cb33cef38
```

For embedding dimension `j`, the effective denominator is:

```text
max(target_reference_std_j, source_training_std_j, 1e-6)
```

The target reference mean remains fixed to windows 0 through 9. The source
anchor is computed from the model's source-training embedding. No target
post-change row or target label enters the scale.

The event artifacts, prototype model, temporal boundaries, robust trace
normalization, and guard candidate grids are unchanged from v0.20.

## Replication boundary

- Seed 11 is a corrected development audit and is saved under the development
  directory.
- Seed 11 is prohibited from the primary aggregate.
- The primary evaluation seeds are 22, 33, 44, 55, 66, 77, 88, 99, 110, and
  121.
- These seeds are computational replicates, not independent datasets or attack
  episodes.

## Automated checks

```text
26 passed in 2.85s
```

This includes the original 24 regression checks and two new tests that verify:

- source-anchored scaling prevents low target-reference variance from
  producing an unbounded score;
- a complete guard benchmark records the source-anchored scale contract,
  diagnostics, and integrity checks.

Additional checks passed:

- 47 YAML files parsed.
- Every YAML mapping key is unique.
- Three notebooks containing 27 code cells compiled.
- All 29 package, test, and notebook-generator Python files compiled.
- The v0.21 protocol matched its recorded SHA-256.
- A version 0.1.11 wheel built and installed successfully.
- The installed wheel imported as `raids-nids 0.1.11` with River 0.25.0.
- The exact validation versions are recorded in
  `requirements-v021-lock.txt`.

## Clean-package checks

The distributable archive contains the cumulative v0.18 through v0.21 source,
tests, configurations, documentation, and notebooks. It contains no raw or
derived dataset, real result directory, virtual environment, cache, bytecode,
or generated egg-info directory.

A fresh extraction independently passed all 26 tests and imported package
version 0.1.11.

## First real-data gate

The user must copy the complete verified
`data\derived\v020_unsw_events` directory into the fresh project. The v0.21
notebook first verifies the suite manifest, both family manifests, all source
and target file hashes, and every event-integrity check.

Both flags remain disabled for the first review:

```python
RUN_CORRECTED_SEED11 = False
RUN_PRIMARY_MATRIX = False
```

The corrected seed-11 audit remains blocked until the copied artifacts pass.
The primary matrix remains blocked until the corrected scale and guard audit
have been reviewed.
