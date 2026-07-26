# v0.19 external dataset and guard-comparison runbook

Run every command from the `raids-nids` project directory. Do not edit any
result CSV or JSON file by hand.

## 1. Update the environment

In Anaconda Prompt:

```bat
conda activate raids-nids
cd C:\Users\ASUS\raids-nids
python -m pip install -e ".[dev]"
python -c "import raids_nids, river; print(raids_nids.__version__, river.__version__)"
```

Expected versions:

```text
0.1.9 0.25.0
```

For an exact direct-dependency replay, use:

```bat
python -m pip install -r requirements-v019-lock.txt
python -m pip install -e .
```

## 2. Place the official raw dataset

Use this exact local path:

```text
C:\Users\ASUS\raids-nids\data\raw\NF-UNSW-NB15-v3.csv
```

Do not rename columns or pre-sort the CSV. The cache builder records the raw
file hash and performs stable chronological ordering itself.

Audit the unchanged raw release:

```bat
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3.yaml
```

## 3. Build the temporal cache

```bat
raids-nids build-unsw-cache ^
  --source-csv data\raw\NF-UNSW-NB15-v3.csv ^
  --output-cache data\derived\v019_unsw_temporal.npz
```

The command must report 2,365,424 rows. Stop if the count differs.

## 4. Build the three frozen events

```bat
raids-nids build-unsw-suite ^
  --source-csv data\raw\NF-UNSW-NB15-v3.csv ^
  --temporal-cache data\derived\v019_unsw_temporal.npz ^
  --output-dir data\derived\v019_unsw_events ^
  --families DoS Exploits Reconnaissance
```

Open:

```text
data\derived\v019_unsw_events\NF-UNSW-NB15-v3-v019-suite-manifest.json
```

Keep every failed event in this manifest. Do not substitute another attack
family after seeing a failure.

## 5. Audit every constructed source and target

Run the matching audits only for events marked `constructed`.

DoS:

```bat
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3_dos_source.yaml
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3_dos_target.yaml
```

Exploits:

```bat
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3_exploits_source.yaml
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3_exploits_target.yaml
```

Reconnaissance:

```bat
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3_reconnaissance_source.yaml
raids-nids audit --dataset configs\datasets\nf_unsw_nb15_v3_reconnaissance_target.yaml
```

Check the following before model runs:

- the source excludes the episode family;
- the first 20,000 target labels are Benign;
- target row 20,000 is the episode family;
- source time is strictly earlier than target time;
- source and target hashes match their event manifest;
- no label, binary label, IP address, raw timestamp, or flow identifier remains
  in the feature set.

## 6. Run seed 11 before the full matrices

Run only the episodes that passed construction and audit.

```bat
raids-nids guard-benchmark --benchmark configs\guard_benchmarks\v019_unsw_dos.yaml
raids-nids guard-benchmark --benchmark configs\guard_benchmarks\v019_unsw_exploits.yaml
raids-nids guard-benchmark --benchmark configs\guard_benchmarks\v019_unsw_reconnaissance.yaml
```

Each run writes one score trace shared by MAD, ADWIN, and Page-Hinkley. Inspect
`summary.json`, `guard_results.csv`, and `guard_candidate_audit.csv`. Do not
change candidates after this step.

## 7. Run the ten paired model seeds

```bat
raids-nids guard-benchmark-matrix --matrix configs\matrices\v019_unsw_dos_guards.yaml
raids-nids guard-benchmark-matrix --matrix configs\matrices\v019_unsw_exploits_guards.yaml
raids-nids guard-benchmark-matrix --matrix configs\matrices\v019_unsw_reconnaissance_guards.yaml
```

The seed-11 run may be repeated. Its deterministic files should have identical
hashes when the software, data, and configuration are unchanged.

## 8. Aggregate the comparison

```bat
raids-nids aggregate-guards ^
  --results-dir results\v019_external_guard_comparison\runs ^
  --output-dir results\v019_external_guard_comparison\aggregate
```

Primary outputs:

```text
results\v019_external_guard_comparison\aggregate\all_guard_results.csv
results\v019_external_guard_comparison\aggregate\guard_summary.csv
results\v019_external_guard_comparison\aggregate\guard_aggregation_manifest.json
```

Do not update the manuscript until the event manifests, all score traces,
candidate audits, and aggregate files have been checked.
