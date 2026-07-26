# Experiment provenance

## Authoritative source selection

The public repository was assembled from five supplied archives. The current
`raids-nids` archive was selected as the only source-code authority because it
contains software version `0.1.11`, the v0.21 protocol, the final tests, and
the completed v0.21 results.

Historical source trees from v0.18, v0.19, and v0.20 were not copied as
duplicate packages. Their version-specific protocols, configs, reports,
notebooks, and evidence were retained.

## Input archive hashes

| Archive | SHA-256 |
|---|---|
| `paper_assets_v018(1).zip` | `40a535334f6f6faf58f5a9bd4ae20dac8022f4356aec507165061585f1739592` |
| `raids-nids.zip` | `7179b551bf1d565b57e419425d696d216276dffec43604b168a08aba685e9f51` |
| `raids-nids-v018-results-archive.zip` | `00b52a7c0df26c4d31ac823edec165f2bb6c6f7a45bdf223e3abd0bb49b441` |
| `raids-nids-v019-failed-archive.zip` | `f45ee8bff1b635c115f23af0235c990a87d6518feac69bf00e434a321be5ffc6` |
| `raids-nids-v020-score-diagnostic-archive.zip` | `94e2d29fe5d7c5793d30605ab56f97c3b789d6d16c952eaceb4d22a2c79ec0eb` |

The standalone paper-assets archive was byte-identical to the
`results/paper_assets_v018/` directory inside the v0.18 results archive.

## Protocol hashes

| Protocol | SHA-256 |
|---|---|
| v0.19 external guard freeze | `1d196eb113a965061cfb9449955067ca5f233a1c23167fe2fe1b06938a097341` |
| v0.20 construction amendment | `04067670316a07ab87310879a7bd64689fe6d7e52758c7dc97d2b5409fe7402b` |
| v0.21 source-anchored score amendment | `8bf4ae3fd53ae31990f5ecac1e431364000004a6c81a7d082c7b740cb33cef38` |

## Evidence decisions

### v0.18

- Preserved all supplied JSON, CSV, YAML, figure, and notebook evidence.
- Preserved all supplied run directories except `model.joblib`.
- Recorded every omitted model's original path, size, and hash.
- Preserved byte-exact historical configs separately.
- Created portable working copies by replacing the fixed
  `C:\Users\ASUS\raids-nids\` prefix with repository-relative paths.

### v0.19

- Preserved the suite manifest and temporal-cache metadata.
- Omitted `v019_unsw_temporal.npz`.
- Preserved the executed failed-construction notebook.
- Retained all three failed families in the denominator.

### v0.20

- Preserved four source/target audit JSON files.
- Preserved both seed-11 result directories, including model binaries.
- Preserved the executed diagnostic notebook.
- Marked all v0.20 detector scores and delays as excluded.
- The supplied archive did not contain the original v0.20 event CSVs or
  event-manifest JSON files. Their verified hashes were recovered from the
  completed v0.21 summaries and recorded in a derived construction summary.
  No missing original manifest was fabricated.

### v0.21

- Preserved both corrected seed-11 development runs.
- Preserved all 20 primary evaluation runs.
- Preserved all three aggregate files.
- Preserved the 600-dpi detector-delay figure.
- Kept seed 11 outside the primary aggregate.

## Environment reconciliation

All 22 saved v0.21 `environment.json` files record the same execution
environment: Python 3.12.13, NumPy 2.5.1, pandas 2.3.3, scikit-learn 1.9.0,
SciPy 1.18.0, and River 0.25.0.

The supplied `requirements-v021-lock.txt` instead listed pandas 2.2.3 and
scikit-learn 1.8.0. Its original bytes are preserved under
`reproducibility/environment_records/`. The root reproduction lock and
`environment.yml` use the versions recorded by the completed runs. Direct
dependencies that were not written to `environment.json` retain the supplied
lock values.

## Files intentionally excluded

- Raw datasets
- Derived source and target datasets
- `v019_unsw_temporal.npz`
- v0.18 serialized models
- Duplicate source trees
- Generated `egg-info`
- Virtual environments, caches, bytecode, and temporary logs
- The five input ZIP files

## Historical paths

Frozen JSON, CSV, and notebook output may contain absolute Windows paths from
the original execution computer. Those fields are retained to protect the
historical record. New executions should use repository-relative working
configs and will write new result paths.

Long run-directory names were shortened in this public package so the
repository remains practical on Windows. Only directory names changed.
`RUN_DIRECTORY_MAP.csv` in each affected evidence root records the exact
source-archive directory and its public-repository location. No frozen file
content was edited during this normalization.
