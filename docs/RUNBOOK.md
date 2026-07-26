# Experiment execution runbook

This file maps the prespecified experiments to code. Run commands from the repository root after installing `.[dev]`.

## Before any model run

1. Obtain each dataset under its licence and record its version and checksum.
2. Edit the dataset YAML path, multiclass label, time field and explicit drop columns.
3. Run `raids-nids audit --dataset <yaml>` on the full data or a declared sample.
4. Complete `docs/dataset_decision_log.csv`.
5. Inspect the source–target common features printed in run summaries.
6. Freeze class harmonization and held-out-class scenarios before comparing methods.

## Code mapping

| Experiment | Configuration or command | Main output |
|---|---|---|
| E00 software smoke | Commands in `README.md` | Audits, run summaries, window traces |
| E01 data audit | `raids-nids audit --dataset ...` | `results/audits/*.json` |
| E02 source control | Every run evaluates the untouched source holdout; use source and target adapters from one environment only after creating non-overlapping files | Source reference F1 and calibration fields |
| E03 cross-environment | `configs/matrices/core_cross_environment.yaml` | Directed transition runs |
| E04 held-out classes | Set `scenario.holdout_labels` to complete prespecified class groups and use `controlled_novelty` | Unknown AUPRC/AUROC and safe-or-correct rate |
| E05 chronology | Set `stream.mode: chronological` and a genuine time field | Trigger delay, false-trigger rate, window trace |
| E06 primary 1% adaptation | Adaptive entries in the core matrix | Normalized recovery area and forgetting |
| E07 budget curve | `configs/matrices/label_budget_curve.yaml` | 0–100% label response curve |
| E08 ablations | `configs/matrices/ablations.yaml` | Component-removal comparisons |
| E09 sensitivity | `configs/matrices/sensitivity.yaml` | Threshold/window/gate sensitivity |
| E10 efficiency | Automatic in every run | Fit, predict, update, memory and model size |
| E11 untouched validation | Clone the pilot config and point target to the frozen external adapter only after method selection | Two final locked-method runs |

## Mandatory dataset-specific decisions

The software cannot decide these scientifically consequential items automatically:

- whether two dataset labels represent the same attack concept;
- which field establishes trustworthy chronological order;
- whether an identifier carries label leakage;
- which complete attack classes form each unknown scenario;
- whether duplicated flows should be collapsed, grouped or retained;
- which third environment is sufficiently compatible for the core study.

Record each decision before the full matrix. Do not tune a decision after viewing primary results.

## Recommended order

1. E00 and tests.
2. E01 on all candidate environments.
3. One seed and two methods on each transition.
4. Freeze data decisions and primary definitions.
5. E03–E06 for five seeds (the supplied three-environment directed core matrix declares 210 runs).
6. Aggregate and select the strongest three methods.
7. E07–E10 only for those methods.
8. Freeze everything, then open E11.

## Stopping rules

- Stop a dataset transition if there is no defensible label mapping or common feature representation.
- Stop an unknown scenario if the withheld class has too little support for windowed evaluation.
- Stop an adaptive method if it violates the cumulative label budget or is scored after update.
- Retain negative and non-significant outcomes in the archive and report them as prespecified.
