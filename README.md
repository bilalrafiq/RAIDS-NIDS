# RAIDS-NIDS

RAIDS-NIDS is the software and frozen evidence package associated with the article:

> **A Leakage-Controlled Fail-Closed Protocol for Prospective Evaluation of Adaptive Network Intrusion Detection**

The repository evaluates adaptive network intrusion detection under chronological
distribution shift, novel-family emergence, fixed target-label budgets, and
fail-closed guard selection. Software version `0.1.11` is the authoritative
codebase for the frozen v0.18 through v0.22 experimental record. Later
manuscript revisions did not alter the frozen measurements.

## Evidence boundary

| Stage | Dataset | Role | Frozen outcome |
|---|---|---|---|
| v0.18 | NF-CSE-CIC-IDS2018-v3 | Core prospective study | DoS passed the primary guard; Web Attacks and Bot failed closed; Infiltration failed temporal construction |
| v0.19 | NF-UNSW-NB15-v3 | Prespecified external construction | 0 of 3 episodes constructed |
| v0.20 | NF-UNSW-NB15-v3 | Amended construction and seed-11 diagnostic | Exploits and Reconnaissance constructed; DoS remained failed; guard scores were invalidated and excluded |
| v0.21 | NF-UNSW-NB15-v3 | Source-anchored exploratory external validation | 20 primary runs and 60 detector evaluations completed |
| v0.22 | NF-UNSW-NB15-v3 Exploits | Prespecified external Gate 4 extension | Gates 1 through 3 passed; 90 Gate 4 runs and their query-provenance audit completed |

The v0.21 evaluation used ten computational seeds for each of two related
episodes. These seeds measure computational stability. They are not
independent networks, deployments, or attack episodes.

## Repository map

```text
RAIDS-NIDS/
├── src/raids_nids/                  # authoritative v0.1.11 package
├── configs/                         # portable experiment configurations
├── notebooks/                       # clean starters and executed records
├── scripts/                         # notebook builders and repository checks
├── tests/                           # regression tests
├── results/frozen/
│   ├── v018_core/                   # v0.18 tables, figures, audits, and runs
│   ├── v021_external_validation/    # v0.21 development and primary results
│   └── v022_unsw_exploits_gate4/    # compact, checksum-bound v0.22 evidence
├── reproducibility/
│   ├── v018_core/                   # byte-exact historical config snapshot
│   ├── v019_failed_construction/    # retained 0/3 construction evidence
│   └── v020_diagnostic_excluded/    # valid construction record and excluded scores
└── docs/                            # data, run, and provenance instructions
```

The working `configs/` copies use repository-relative paths. Byte-exact v0.18
configurations, including their original author-machine paths, remain under
`reproducibility/v018_core/config_snapshot/original_configs/` so historical
hashes remain auditable.

## Set up

The package declares Python 3.11 or later. The frozen v0.21 runs recorded
Python 3.12.13.

### Conda

```bash
conda env create -f environment.yml
conda activate raids-nids
```

### Virtual environment

```bash
python -m venv .venv
```

On Windows:

```powershell
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

On Linux or macOS:

```bash
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

## Verify the repository

```bash
python scripts/verify_repository.py
python scripts/verify_v022_publication_evidence.py \
  --root results/frozen/v022_unsw_exploits_gate4 \
  --expected-archive-sha256 77c87be900e732fb64c505ac01b33b6dd8243f96845e7500317a200e4145c6ab \
  --expected-archive-size 114039766
python -m pytest -q -p no:cacheprovider
```

For a frozen release package, also verify every included file:

```bash
python scripts/verify_repository.py --checksums
```

The repository check confirms the evidence counts, seed exclusions, guard
outcomes, protocol hashes, notebook structure, YAML validity, and GitHub file
size limit.

## Verify the pipeline with synthetic data

```bash
raids-nids generate-synthetic --output-dir data/synthetic
raids-nids audit --dataset configs/datasets/synthetic_source.yaml
raids-nids audit --dataset configs/datasets/synthetic_target.yaml
raids-nids run --experiment configs/experiments/smoke_static.yaml
raids-nids run --experiment configs/experiments/smoke_adaptive.yaml
raids-nids aggregate --results-dir results/runs --output-dir results/aggregate
```

Synthetic outputs only test software execution. They are not paper evidence.

## Real datasets

Raw and derived datasets are not redistributed. Download the two official
NetFlow v3 datasets, verify the recorded hashes where available, and place
them under `data/raw/`.

See:

- [Data acquisition](docs/DATA_ACQUISITION.md)
- [Reproducibility procedure](docs/REPRODUCIBILITY.md)
- [Experiment provenance](docs/EXPERIMENT_PROVENANCE.md)
- [Frozen results guide](docs/RESULTS_GUIDE.md)
- [Public repository audit](docs/REPOSITORY_AUDIT.md)
- [v0.22 public evidence packaging](docs/V022_PUBLIC_EVIDENCE_PACKAGING.md)

## Frozen v0.21 result

All 20 primary model runs completed with every recorded integrity check
passing. All 60 guard evaluations passed the pre-change guard and detected a
post-change shift.

| Detector | Exploits delay, median (range) | Reconnaissance delay, median (range) |
|---|---:|---:|
| Page-Hinkley | 0 (0-0) | 1 (1-7) |
| MAD | 8 (8-8) | 7 (7-7) |
| ADWIN | 93 (92-93) | 92 (91-94) |

A delay of `0` means detection after processing the first 500-flow
post-change window. The detectors identify an unlabeled distributional change
associated with family onset; they do not identify the attack family itself.
The evidence does not establish universal detector superiority.

## Frozen v0.22 result boundary

The prespecified NF-UNSW-NB15-v3 Exploits extension completed ten Gate 2/3
runs and 90 Gate 4 runs across the frozen ten-seed, nine-method matrix. Its
post-run query-provenance audit passed all 90 run-level count, uniqueness,
hash, and seed checks. These seeds measure computational stability and are not
independent networks or deployments.

The repository carries a 15 MB compact copy of the evidence. It retains 635
source files byte for byte, maps 100 long run directories to short identifiers,
and inventories the 100 model binaries and six logs kept only in the separate
full archive.

## Result integrity

Do not edit frozen JSON or CSV files. Historical files may contain original
Windows paths; these are provenance fields, not required current locations.
Use the repository-level `MANIFEST.sha256` and the version-specific manifests
to verify bytes.

Several earlier frozen directories include `model.joblib`. Joblib uses
pickle-based serialization, so only load model files obtained from a trusted
release after checking their SHA-256 values. The compact v0.22 directory does
not include model binaries or logs; their hashes and archive paths are recorded
in `OMITTED_FILES.csv`.

## Citation

Use the metadata in [CITATION.cff](CITATION.cff). Once a public GitHub release
and archival DOI exist, update that file and the paper's Data and Materials
Availability statement with the immutable release identifier.

## License

The code and repository-authored materials are released under the
[MIT License](LICENSE). Third-party datasets retain their original terms and
are not included here.
