# Frozen results guide

## v0.18 core study

Paper-facing assets:

```text
results/frozen/v018_core/paper_assets_v018/
```

Key files:

- `table_cross_episode_status_v018.csv`
- `table_guard_feasibility_all10_v018.csv`
- `table_dos_performance_all10_v018.csv`
- `table_dos_query_sets_all10_v018.csv`
- `table_dos_key_contrasts_all10_v018.csv`
- four figures in PNG, PDF, and SVG formats

Underlying audit records:

```text
results/frozen/v018_core/audits/
```

Run-level records:

```text
results/frozen/v018_core/runs/
```

The archive contains historical development records in addition to the
paper-facing subset. Use the paper-assets manifests and protocol ledgers to
identify the inferential evidence.

## v0.19 failed construction

```text
reproducibility/v019_failed_construction/
```

The suite manifest records zero constructed episodes for DoS, Exploits, and
Reconnaissance. No v0.19 real guard result exists.

## v0.20 excluded diagnostic

```text
reproducibility/v020_diagnostic_excluded/
```

The event-construction result remains valid: Exploits and Reconnaissance
constructed, while DoS failed. The target-reference-only score traces and
detector outputs are invalid diagnostic evidence and must not enter any
primary result table.

## v0.21 external validation

Development seed 11:

```text
results/frozen/v021_external_validation/development/
```

Primary evaluation:

```text
results/frozen/v021_external_validation/evaluation/
```

Final aggregate:

```text
results/frozen/v021_external_validation/evaluation/aggregate/
```

Primary seed set:

```text
22, 33, 44, 55, 66, 77, 88, 99, 110, 121
```

Each family has ten model runs and thirty detector rows. Seed 11 is absent
from the aggregate.

## v0.22 NF-UNSW Exploits Gate 4 extension

Compact public evidence:

```text
results/frozen/v022_unsw_exploits_gate4/
```

The final records report passed Gates 1, 2, and 3 and 90 defined Gate 4 runs.
The query-provenance audit passed all 90 run-level checks. Use
`RUN_DIRECTORY_MAP.csv` to resolve the short public run identifiers and
`SOURCE_FILE_MAP.csv` to recover each original evidence path. The compact copy
omits 100 `model.joblib` files and six logs. Their original paths, archive
member paths, sizes, and SHA-256 values are in `OMITTED_FILES.csv`.

The full evidence archive is separate from Git because it is 114,039,766
bytes. Its SHA-256 is
`77c87be900e732fb64c505ac01b33b6dd8243f96845e7500317a200e4145c6ab`.

## Reporting rules

1. Treat failures as results.
2. Keep the v0.18 core study and v0.21 external extension separate.
3. Keep the two v0.21 families separate.
4. Describe seed percentages as computational stability summaries.
5. Do not report v0.20 detector outcomes as corrected results.
6. Do not replace the failed DoS construction.
7. Do not describe guard triggers as attack-family classification.
8. Keep the v0.22 Gate 4 extension distinct from the v0.21 score-only external
   evaluation.
