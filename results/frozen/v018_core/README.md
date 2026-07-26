# v0.18 frozen evidence

This directory contains the complete supplied v0.18 result tree except the
211 serialized `model.joblib` files.

Included scope before repository-level manifests are added:

- 211 run directories
- 1,456 files
- 184 audit and protocol files
- 22 paper-facing assets
- 5 aggregate files
- 2 analysis files
- 4 paired five-seed files

Use `paper_assets_v018/` for manuscript tables and figures. Use `audits/` and
`runs/` to trace each paper-facing value to the underlying frozen evidence.

The run tree also contains historical development experiments. Presence in
this directory does not make every run part of primary inference. Follow the
protocol freezes, episode ledger, paper-assets manifests, and manuscript
evidence boundary.

## Omitted models

The original archive contained 211 serialized models totaling approximately
298 MB. They were omitted because the tabular evidence, configs, summaries,
window traces, environments, and recorded model hashes are sufficient to audit
the reported values without bloating the public Git history.

`OMITTED_MODELS.csv` records each omitted file's original relative path, byte
size, and SHA-256.

## Configurations

Portable v0.18 working configurations are merged into the repository-level
`configs/` tree. The byte-exact originals remain at:

```text
reproducibility/v018_core/config_snapshot/original_configs/
```

Do not compare a portable working config's hash with a historical original
config hash.
