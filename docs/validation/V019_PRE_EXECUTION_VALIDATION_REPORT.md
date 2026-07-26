# RAIDS-NIDS v0.19 validation report

**Validation date:** 23 July 2026  
**Package version:** 0.1.9  
**Purpose:** engineering validation before opening NF-UNSW-NB15-v3 outcomes

## Frozen protocol

- Protocol: `configs/protocols/v019_external_guard_freeze.yaml`
- SHA-256:
  `1d196eb113a965061cfb9449955067ca5f233a1c23167fe2fe1b06938a097341`
- External dataset: NF-UNSW-NB15-v3
- Prespecified episodes: DoS, Exploits, Reconnaissance
- Guard comparators: MAD, ADWIN, Page-Hinkley
- River version: 0.25.0

## Automated checks

```text
22 passed in 2.81s
```

The test suite covers:

- the original v0.18-compatible data, model, metric, query, and guard behavior;
- source-only preprocessing and prediction-before-update controls;
- guard-safe MAD selection;
- a paired score-trace comparison across all three guards;
- ADWIN and Page-Hinkley post-change detection on a controlled shift;
- guard-result aggregation;
- NF-UNSW temporal indexing;
- selection of the earliest eligible held-out-family episode;
- exclusion of prior emerging-family rows from the historical source;
- source-target temporal separation and file hashing.

Python compilation, all 27 YAML files, and all notebook code cells also passed
syntax validation.

## End-to-end engineering smoke test

One synthetic run used 120 windows and one shared shift-score trace:

| Guard | Guard status | Detected change | Delay |
|---|---|---:|---:|
| MAD | Passed | Yes | 1 window |
| ADWIN | Passed | Yes | 6 windows |
| Page-Hinkley | Passed | Yes | 0 windows |

These values only verify software execution. They are not research evidence and
must not appear in the manuscript.

The smoke run produced:

- resolved configuration;
- score trace;
- candidate-level audit;
- three-row guard comparison;
- serialized model;
- environment record;
- SHA-256 values;
- aggregate result and summary tables.

## Remaining execution boundary

The official NF-UNSW-NB15-v3 CSV is not present in this workspace. No real
v0.19 event, guard outcome, detection delay, or adaptive result has been
generated here.

The next valid action is to place the unchanged official CSV at
`data/raw/NF-UNSW-NB15-v3.csv` and run
`RAIDS_NIDS_v019_External_Guard_Starter.ipynb` in order. The manuscript must
remain on the frozen v0.18 results until the real event manifests and all paired
guard runs have passed audit.
