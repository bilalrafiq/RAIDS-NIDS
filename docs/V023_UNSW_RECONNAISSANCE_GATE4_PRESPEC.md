# RAIDS-NIDS v0.23 Reconnaissance Gate 4 prespecification

## Frozen scientific boundary

v0.23 is a prespecified second-episode replication using the constructed
NF-UNSW-NB15-v3 Reconnaissance episode. It is not untouched validation. The
v0.21 Reconnaissance detector results and the v0.22 Exploits Gate 4 results
were observed before this protocol was written.

Reconnaissance and Exploits come from the same raw NF-UNSW-NB15-v3 trace.
They provide distinct frozen event episodes, but they are not independent
network environments. The ten model seeds measure computational sensitivity
within this one recorded stream. They are not ten independent deployments.

The prespecification is based on the frozen v0.22 merge commit:

```text
00b90bfb7a6f3aeb9eebb14af12fae228b529702
```

No v0.23 Gate 4 outcome had been observed when this file and the associated
machine-readable protocol were prepared on 2026-08-29.

## Permitted episode changes

The v0.23 controller changes only the episode-specific data paths, family and
scenario identifiers, expected artifact hashes, event timestamp, onset count,
run names, and v0.23 output directory. It also narrows the statistical family
to the three contrasts declared below.

The following execution settings remain equal to v0.22:

- source-only preprocessing with PCA 32, rejection quantile 0.95, and memory
  1,000 per class;
- source-anchored maximum score scaling from v0.21;
- 500-flow detector windows and 5,000-flow evaluation blocks;
- reference windows 0 to 9, calibration windows 10 to 29, guard windows 30 to
  39, and monitoring from window 40;
- MAD candidates 3, 4, 5, and 6, with two consecutive exceedances;
- model seeds, query seed, selectors, budgets, update rules, and static
  baseline;
- prediction and scoring before any query or update;
- fail-closed execution and retention of failed branches.

The v0.21 Reconnaissance guard results cannot authorize Gate 4 because they
used PCA 0 and memory 500. v0.23 therefore reruns Gates 2 and 3 with the core
PCA 32 and memory 1,000 profile before Gate 4 can start.

## Frozen Reconnaissance artifact

| Field | Frozen value |
|---|---|
| Dataset | `NF-UNSW-NB15-v3` |
| Emerging family | `Reconnaissance` |
| Event time | `2015-02-18 01:06:32.190000` |
| Source rows | 500,000 |
| Target rows | 120,000 |
| Warm-up rows | 20,000 |
| Post-change rows | 100,000 |
| Reconnaissance count in first 500 post-change rows | 6 |
| Reconnaissance count in first 5,000 post-change rows | 55 |
| Raw SHA-256 | `4ebb97bd74412d566137d95a6fc3ffd8f374f1cf8cfe204d007848e7a668f9b5` |
| Event-manifest SHA-256 | `856f165fd8cb34a0db91dfa574bda106bd55c5d7d0820a0445cb56c1a8a9ae13` |
| Source SHA-256 | `23a046f34ceb9e43b434f8b633d29d7d9f63c34944387fb6e62467f8ec3acedf` |
| Target SHA-256 | `d4157b6246db7cb254df1406c0f59c81f7b6e605ed62105b0ec196e09b70940e` |

Expected local inputs:

```text
data/derived/v020_unsw_events/NF-UNSW-NB15-v3-reconnaissance-manifest.json
data/derived/v020_unsw_events/NF-UNSW-NB15-v3-reconnaissance-historical-source.csv
data/derived/v020_unsw_events/NF-UNSW-NB15-v3-reconnaissance-heldout-target.csv
data/derived/v020_unsw_events/NF-UNSW-NB15-v3-v020-suite-manifest.json
```

If reconstruction is required, the controller also verifies the frozen raw
dataset hash before rebuilding the complete v0.20 family suite.

## Gates and run grid

Gate 1 verifies the event manifest, hashes, row geometry, timestamps,
chronological order, emerging-family exclusion from the historical source,
warm-up support, and frozen onset counts.

Gate 2 constructs the source-only model and source-anchored score trace. A
numerically invalid score stops the branch.

Gate 3 selects the smallest prespecified MAD multiplier with no persistent
held-out pre-change guard trigger. Failure makes Gate 4 outcomes undefined for
that model seed. ADWIN and Page-Hinkley remain secondary detector comparisons.

Gate 4 is permitted only for MAD-admissible seeds. Its maximum run grid is:

| Component | Count |
|---|---:|
| Gate 2 and Gate 3 guard runs | 10 |
| Static Gate 4 runs | 10 |
| Adaptive Gate 4 runs | 80 |
| Maximum defined Gate 4 runs | 90 |

The model seeds are `11, 23, 37, 53, 71, 83, 97, 109, 127, 149`. The query
seed is 11. The adaptive cells are the full product of:

- selector: `random_nested`, `uncertainty_diversity`;
- label budget: 50, 200;
- update rule: `replay`, `source_anchored`.

## Outcomes and statistical tests

The primary outcome is `primary_normalized_recovery_area`. Three paired
model-seed contrasts form the complete confirmatory family:

1. uncertainty-diversity minus random, marginal over budget and update rule;
2. budget 200 minus budget 50, marginal over selector and update rule;
3. uncertainty-diversity at budget 200 minus static, marginal over update rule.

Each contrast uses an exact two-sided paired sign-flip test over all sign
assignments. Zero differences remain in the test. An all-zero contrast has
`p = 1`. Holm adjustment applies once across these three primary tests.

The same three contrasts are computed for two secondary outcomes:

- `global_novel_exact_recall`;
- `mean_source_forgetting`.

These six secondary analyses are labeled non-confirmatory. They are not added
to the primary Holm family. Bootstrap confidence intervals use 100,000 paired
model-seed resamples with bootstrap seed 2026.

## Leakage and provenance controls

The controller requires the following for every defined Gate 4 run:

- preprocessing fitted only on the historical source;
- detector calibration and guard selection without target labels;
- score scaling without post-change target rows;
- predictions recorded before queries and updates;
- unique queried target rows and exact reconciliation with labels queried;
- fixed query seed 11;
- ordered query indices and their little-endian signed-int64 SHA-256;
- negative polarity for `initial_model_saw_novel_target_class_names`;
- every other required integrity field equal to true.

The post-run audit must reconcile 90 unique seed-method summaries, 40
identical query-selection pairs across update rules, 20 Random B50 subsets of
Random B200, and 10 static zero-query runs. Any problem fails Gate 4 packaging.

## Pre-outcome verification

Run these commands only after the prespecification files are committed on a
clean branch:

```powershell
conda activate raids-nids
Set-Location C:\R\RAIDS-NIDS
$env:PYTHONDONTWRITEBYTECODE = "1"
python scripts\verify_v023_prespecification.py --repo-root .
python -m pytest -q -p no:cacheprovider
python scripts\verify_repository.py --checksums
python scripts\run_v023_unsw_reconnaissance_gate4.py --repo-root . --dry-run --skip-tests
Remove-Item Env:PYTHONDONTWRITEBYTECODE
```

The dry run may write `preflight.json` and logs under the dedicated v0.23
evidence directory. It does not execute Gates 1 to 4 or compute outcomes.

Before the real run, record:

```powershell
git status --short --branch
git rev-parse HEAD
```

`git status` must show no changes outside the dedicated v0.23 evidence path.

## Outcome-generating command

When the frozen derived Reconnaissance files already exist:

```powershell
python scripts\run_v023_unsw_reconnaissance_gate4.py --repo-root .
```

When they must be reconstructed from the exact raw dataset:

```powershell
python scripts\run_v023_unsw_reconnaissance_gate4.py --repo-root . --build-events-if-missing
```

Do not use `--allow-dirty` for the real run. Keep v0.22 results, the v0.22
Release assets, and all existing frozen directories unchanged.

## Expected retained outputs

If all gates pass, the dedicated local evidence directory contains gate
records, run summaries, score traces, metrics, plots, three primary tests, six
secondary analyses, the query-provenance audit, manuscript snippets, final
verification, and checksums.

If a gate fails, retain its audit records. Downstream outcomes remain undefined
and must not be replaced with estimates from an inadmissible branch.
