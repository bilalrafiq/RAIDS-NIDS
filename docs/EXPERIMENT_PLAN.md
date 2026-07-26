# Complete experiment plan

## Fixed scientific question

Can a network intrusion detector reject unfamiliar attacks and recover with a very small target-label budget while retaining previously learned classes under chronological and cross-environment changes?

The benchmark is the main contribution. The expandable prototype learner is a reference adaptive method, not the sole source of novelty.

## Factors and outcomes

| Factor | Levels |
|---|---|
| Evaluation track | within-distribution control; chronological; cross-environment; novel-class exposure |
| Method family | static classical; static neural; anomaly; open-set; semi-supervised; online adaptive; proposed; oracle |
| Label budget | 0%, 0.5%, 1%, 5%, 100% oracle |
| Unknown scenario | at least three complete held-out class groups per environment |
| Seed | 11, 22, 33, 44, 55 |
| Primary outcome | normalized recovery area at 1% labels |
| Secondary outcomes | known macro-F1, unknown AUPRC, recovery time, forgetting, false-trigger rate, calibration, processing time |

## E00 — software smoke test

**Purpose:** prove that every command, file and metric works end to end.

- Generate synthetic source and target streams.
- Run audit, static methods, open-set method and adaptive method.
- Verify that unknown classes are absent from initial training.
- Verify that no more labels are queried than the configured budget.
- Verify that all output files can be aggregated.

**Evidence status:** engineering only; never include performance in the paper.

## E01 — dataset audit and eligibility

Run before all real experiments.

For each dataset record:

- licence and persistent identifier;
- row/feature count and label hierarchy;
- exact duplicate count;
- missing and infinite values;
- constant and near-unique columns;
- identifier-like and label-like columns;
- class support and imbalance;
- chronological field availability;
- source–target feature intersection.

**Go criterion:** at least three defensible environments with a reproducible common feature representation. If only two pass, retain two and increase the number of prespecified unknown-class scenarios.

## E02 — within-distribution control

**Purpose:** establish an upper-bound sanity check and confirm that preprocessing is valid.

- Train/validation/test split using source observations only.
- Group duplicates within one partition.
- Run logistic regression, random forest, compact MLP and prototype classifier.
- Five seeds.
- Report macro-F1, MCC, balanced accuracy, per-class recall, false-positive rate, expected calibration error and processing time.

This experiment is not the primary claim.

## E03 — zero-shot cross-environment generalization

**Purpose:** quantify the generalization gap before adaptation.

- Train in environment A and evaluate without updates in B and C.
- Repeat directed transitions where class mapping is defensible.
- Do not recalibrate preprocessing or rejection thresholds on target labels.
- Report source-test versus target-window degradation, known macro-F1, MCC, unknown AUPRC and calibration.

Expected paper figure: source-by-target performance matrix.

## E04 — open-world novel-class exposure

**Purpose:** test rejection of complete classes missing from source training.

- Prespecify at least three held-out class groups per environment.
- Remove every held-out-class observation from source train and validation.
- Construct stable known-only windows followed by mixed known/unknown windows.
- Compare closed-set confidence, prototype rejection and the adaptive reference method before any labels are queried.
- Report unknown AUPRC, AUROC, false-known rate, false-unknown rate, coverage and selective risk.

Primary unknown metric: AUPRC because attack prevalence can be low.

## E05 — chronological resilience

**Purpose:** measure degradation, shift detection and recovery over time.

- Preserve reliable chronological ordering.
- Fit all preprocessing on the historical source period only.
- Record predictions before every update.
- Compare the static model, periodic-update baseline, shift-gated prototype learner and strongest streaming baseline.
- Report initial degradation, trigger delay, false triggers, normalized recovery area and time-to-recovery.

Do not describe a dataset transition as concept drift. Report the observed change type precisely.

## E06 — limited-label adaptation (primary experiment)

**Purpose:** test recovery under the primary 1% label budget.

- Same sequential streams and seeds for every adaptive method.
- Cumulative labels may not exceed 1% of target observations seen so far.
- Select labels using uncertainty plus diversity; compare with random selection.
- Evaluate source holdout after every update to measure forgetting.
- Primary paired comparison: proposed method versus strongest eligible adaptive baseline on normalized recovery area.

## E07 — label-budget curve

Run the strongest three deployable methods at:

- 0%;
- 0.5%;
- 1%;
- 5%;
- 100% oracle after exposure.

Report recovery gain per 100 labels and the complete budget–recovery curve. The oracle is an upper bound, not an operational comparator.

## E08 — ablation study

Remove one component at a time:

1. unknown/abstention gate;
2. shift gate (update periodically instead);
3. uncertainty–diversity selection (use random labels);
4. replay memory;
5. optional pseudo-labelled high-confidence updates;
6. PCA representation.

Retain a simpler method if the complete method does not outperform it under the primary budget.

## E09 — sensitivity analysis

Vary:

- unknown rejection quantile: 0.90, 0.95, 0.975;
- window size: 250, 500, 1,000, subject to dataset scale;
- recovery threshold: 0.90 and 0.95 of the pre-change reference;
- drift trigger threshold;
- natural versus controlled attack prevalence;
- source memory per class.

Primary definitions must be frozen before full runs; sensitivity analysis must not replace them.

## E10 — efficiency

Under matched data and window sizes record:

- fit time;
- prediction time per observation;
- update time per event;
- peak process memory where available;
- serialized model size;
- number of model updates;
- number of labelled observations.

No specialized deployment hardware is required.

## E11 — untouched external validation

After method and threshold choices are frozen:

- open one additional environment;
- run only the top two deployable methods;
- do not tune on this environment;
- report whether the primary ranking and effect direction hold.

## Statistical plan

- Five independent seeds for every stochastic primary experiment.
- Dataset transition or unknown-group scenario is the inferential unit, not individual rows.
- Report mean, standard deviation, median and bootstrap 95% intervals.
- Use paired tests on identical scenarios and seeds.
- Use a Friedman test for complete multi-method blocks.
- Use multiplicity-controlled paired post-hoc tests when the omnibus result warrants them.
- Report paired effect sizes and confidence intervals.
- Publish all prespecified outcomes.

## Run-count control

Core suite:

- 3 environments;
- 3 unknown scenarios per environment;
- 5 seeds;
- 7 deployable method families;
- primary 1% budget.

This is 315 method–scenario–seed evaluations before cross-environment directionality. Run label sensitivity and ablations only on the strongest methods to keep the project finishable.

## Decision gates

| Date | Gate | Minimum evidence |
|---|---|---|
| 31 July | Data eligibility | Three environments or approved two-environment fallback |
| 31 August | Baseline integrity | Reproducible leakage-controlled baselines |
| 30 September | Adaptive signal | At least one adaptive method improves recovery area, or a clear negative benchmark result |
| 20 October | Primary completeness | All core streams and five seeds complete |
| 10 November | Contribution test | Resilience evaluation yields a stable ranking or failure insight beyond static F1 |
| 30 November | Submission readiness | Complete draft, repository, supplement and internal review |
| 15 December | Internal deadline | Submit with a deadline buffer |

