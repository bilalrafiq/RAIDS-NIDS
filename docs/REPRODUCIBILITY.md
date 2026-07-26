# Reproducibility procedure

This procedure separates software verification, event reconstruction, and
paper-result reproduction. Do not tune a frozen protocol after inspecting an
outcome.

## 1. Verify the package

```bash
python scripts/verify_repository.py --checksums
pytest -q
```

Expected software version:

```text
raids-nids 0.1.11
river 0.25.0
```

## 2. Run the synthetic smoke test

```bash
raids-nids generate-synthetic --output-dir data/synthetic
raids-nids audit --dataset configs/datasets/synthetic_source.yaml
raids-nids audit --dataset configs/datasets/synthetic_target.yaml
raids-nids run --experiment configs/experiments/smoke_static.yaml
raids-nids run --experiment configs/experiments/smoke_adaptive.yaml
```

These runs test the program only. Do not combine them with paper results.

## 3. Reproduce v0.18

1. Acquire NF-CSE-CIC-IDS2018-v3 as described in
   `docs/DATA_ACQUISITION.md`.
2. Review the executed v0.18 notebooks and the frozen protocol records under
   `results/frozen/v018_core/audits/`.
3. Use the portable working configs under `configs/`.
4. Compare reproduced files with the paper-facing tables under
   `results/frozen/v018_core/paper_assets_v018/`.

The exact original v0.18 configuration bytes remain under
`reproducibility/v018_core/config_snapshot/original_configs/`. Their absolute
Windows paths are historical provenance. Do not use those paths on a new
computer.

Serialized v0.18 models were omitted to keep the public repository practical.
Their original paths, sizes, and SHA-256 values are recorded in
`results/frozen/v018_core/OMITTED_MODELS.csv`.

## 4. Reproduce v0.19

1. Place the verified NF-UNSW-NB15-v3 CSV at
   `data/raw/NF-UNSW-NB15-v3.csv`.
2. Read `docs/V019_EXTERNAL_GUARD_PROTOCOL.md`.
3. Run the clean v0.19 notebook.
4. Confirm that all three prespecified families fail the original all-Benign
   warm-up construction rule.

The frozen suite manifest records `0/3` constructed episodes. This failure is
part of the prospective denominator.

## 5. Reconstruct v0.20

1. Read `docs/V020_PROTOCOL_AMENDMENT.md`.
2. Run
   `notebooks/v020/RAIDS_NIDS_v020_Amended_External_Guard_Starter.ipynb`.
3. Confirm:
   - DoS: failed construction
   - Exploits: constructed
   - Reconnaissance: constructed
4. Verify every reconstructed event file against
   `reproducibility/v020_diagnostic_excluded/construction_summary.json`.

The archived v0.20 seed-11 score traces are diagnostic evidence only. Their
target-reference-only scaling was dominated by near-zero-variance dimensions,
so the detector outcomes are excluded from primary inference.

## 6. Reproduce v0.21

Read these files first:

```text
configs/protocols/v021_source_anchored_score_amendment.yaml
docs/V021_SCORE_AMENDMENT.md
docs/V021_RUNBOOK.md
```

The corrected scale for embedding dimension `j` is:

```text
max(target_reference_std_j, source_training_std_j, 1e-6)
```

Run the clean notebook:

```text
notebooks/v021/RAIDS_NIDS_v021_Source_Anchored_Guard_Starter.ipynb
```

The execution order is:

1. Verify the protocol and reconstructed v0.20 event hashes.
2. Run seed 11 only as the corrected development audit.
3. Keep seed 11 outside the primary evaluation directory.
4. Run seeds `22, 33, 44, 55, 66, 77, 88, 99, 110, 121`.
5. Aggregate only the primary evaluation directory.

Expected primary scope:

- 20 model runs
- 60 detector rows
- 2 scenarios
- 3 detectors
- 10 approved seeds per scenario
- no seed 11

## 7. Compare reproduced v0.21 results

Use:

```text
results/frozen/v021_external_validation/evaluation/aggregate/all_guard_results.csv
results/frozen/v021_external_validation/evaluation/aggregate/guard_summary.csv
results/frozen/v021_external_validation/evaluation/aggregate/guard_aggregation_manifest.json
```

All 60 primary detector rows should have:

```text
guard_status = passed
post_change_detected = True
analysis_role = heldout_computational_evaluation
score_scaling_contract = 1.0-v021-source-anchored-max-scale
```

## 8. Interpretation limits

- Seeds are computational replicates, not independent deployment samples.
- Report Exploits and Reconnaissance separately.
- Do not turn the observed 100% pass or detection counts into deployment
  probabilities.
- A delay of zero means the first post-change 500-flow window triggered.
- Guards detect an unlabeled distributional change, not an attack-family
  identity.
- v0.21 is exploratory post-diagnostic validation, not untouched external
  confirmation.
