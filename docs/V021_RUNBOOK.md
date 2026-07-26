# RAIDS-NIDS v0.21 Windows runbook

## Folder preparation

Keep the complete v0.20 folder and its seed-11 diagnostic as:

```text
C:\Users\ASUS\raids-nids-v020-score-diagnostic-archive
```

Extract the v0.1.11 package so the new project root is:

```text
C:\Users\ASUS\raids-nids
```

Copy this complete directory from the archived project into the new project:

```text
data\derived\v020_unsw_events
```

It must include the suite manifest, the two constructed family manifests, and
their source and target CSV files. Do not copy the v0.20 `results` directory
into the new project.

## Install and verify

```bat
conda activate raids-nids
cd /d C:\Users\ASUS\raids-nids
python -m pip install -e ".[dev]"
python -c "import raids_nids, river; print(raids_nids.__version__); print(raids_nids.__file__); print(river.__version__)"
python -m pytest -q
```

Expected versions:

```text
0.1.11
0.25.0
```

Then start:

```bat
python -m jupyter notebook RAIDS_NIDS_v021_Source_Anchored_Guard_Starter.ipynb
```

Use the kernel connected to the `raids-nids` Conda environment.

## First execution boundary

Run through the artifact verification and control cell only. Keep:

```python
RUN_CORRECTED_SEED11 = False
RUN_PRIMARY_MATRIX = False
```

After the artifacts pass, run only the corrected seed-11 audit. The primary
matrix remains blocked until the saved scale diagnostics, candidate audits,
and guard results have been reviewed.
